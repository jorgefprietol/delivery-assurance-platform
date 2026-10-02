"""Transactional use cases and traceability rules."""

from datetime import UTC, datetime
from uuid import uuid4

from app.auth import Actor
from app.domain import DomainError, evaluate_gate, snapshot_digest, transition, validate_commit
from app.ports import Repository


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class DeliveryService:
    def __init__(self, repository: Repository, actor: Actor):
        self.repo = repository
        self.actor = actor

    def record(self, kind: str, project_id: str | None, fields: dict) -> dict:
        item = {
            **fields,
            "id": str(uuid4()),
            "project_id": project_id,
            "version": 1,
            "created_at": timestamp(),
            "created_by": self.actor.subject,
        }
        self.repo.save(kind, item)
        self.event(project_id or item["id"], f"{kind}.created", item["id"], 1)
        return item

    def event(self, project_id: str, action: str, entity_id: str, version: int) -> None:
        self.repo.audit(
            {
                "id": str(uuid4()),
                "project_id": project_id,
                "action": action,
                "entity_id": entity_id,
                "version": version,
                "at": timestamp(),
                "actor": self.actor.subject,
                "role": self.actor.role,
            }
        )

    def project(self, fields: dict) -> dict:
        self.actor.require("engineer")
        with self.repo.atomic():
            return self.record("project", None, fields)

    def requirement(self, project_id: str, fields: dict) -> dict:
        self.actor.require("engineer")
        with self.repo.atomic():
            self.repo.get("project", project_id)
            return self.record(
                "requirement",
                project_id,
                {
                    **fields,
                    "status": "draft",
                    "revision": 1,
                    "approved_by": None,
                    "implemented_by": None,
                    "implementation_sha": None,
                    "verified_sha": None,
                    "verified_by": None,
                },
            )

    def risk(self, project_id: str, fields: dict) -> dict:
        self.actor.require("engineer")
        with self.repo.atomic():
            self.repo.get("project", project_id)
            return self.record("risk", project_id, {**fields, "status": "open", "mitigation": ""})

    @staticmethod
    def check_version(item: dict, expected: int) -> None:
        if item["version"] != expected:
            raise DomainError("This record changed; reload before saving")

    def advance(
        self, identifier: str, expected: int, target: str, commit_sha: str | None = None
    ) -> dict:
        self.actor.require("reviewer" if target == "approved" else "engineer")
        with self.repo.atomic():
            item = self.repo.get("requirement", identifier)
            self.check_version(item, expected)
            transition(item["status"], target)
            if target == "approved":
                self.actor.independent_of(item.get("created_by"))
                if commit_sha is not None:
                    raise DomainError("Record the commit when marking implementation", 422)
                item["approved_by"] = self.actor.subject
            else:
                self.actor.independent_of(item.get("approved_by"))
                item.update(
                    implemented_by=self.actor.subject,
                    implementation_sha=validate_commit(commit_sha),
                )
            item.update(status=target, version=item["version"] + 1)
            self.repo.save("requirement", item)
            self.event(item["project_id"], f"requirement.{target}", identifier, item["version"])
            return item

    def revise(self, identifier: str, expected: int, fields: dict) -> dict:
        self.actor.require("engineer")
        with self.repo.atomic():
            item = self.repo.get("requirement", identifier)
            self.check_version(item, expected)
            item.update(fields)
            item.update(status="draft", revision=item["revision"] + 1, version=item["version"] + 1)
            item.update(
                approved_by=None,
                implemented_by=None,
                implementation_sha=None,
                verified_sha=None,
                verified_by=None,
            )
            self.repo.save("requirement", item)
            self.event(item["project_id"], "requirement.revised", identifier, item["version"])
            return item

    def evidence(self, identifier: str, expected: int, fields: dict) -> dict:
        self.actor.require("reviewer")
        with self.repo.atomic():
            item = self.repo.get("requirement", identifier)
            self.check_version(item, expected)
            if item["status"] not in {"implemented", "verified"}:
                raise DomainError("Evidence requires an implemented requirement")
            self.actor.independent_of(item.get("implemented_by"))
            if validate_commit(fields.get("commit_sha")) != item.get("implementation_sha"):
                raise DomainError("Evidence commit must match the current implementation")
            evidence = self.record(
                "evidence",
                item["project_id"],
                {
                    **fields,
                    "requirement_id": identifier,
                    "revision": item["revision"],
                },
            )
            item.update(
                status="verified" if fields["outcome"] == "passed" else "implemented",
                version=item["version"] + 1,
                verified_sha=fields["commit_sha"] if fields["outcome"] == "passed" else None,
                verified_by=self.actor.subject if fields["outcome"] == "passed" else None,
            )
            self.repo.save("requirement", item)
            self.event(item["project_id"], "requirement.tested", identifier, item["version"])
            return evidence

    def mitigate(self, identifier: str, expected: int, mitigation: str) -> dict:
        self.actor.require("engineer")
        with self.repo.atomic():
            item = self.repo.get("risk", identifier)
            self.check_version(item, expected)
            item.update(mitigation=mitigation, status="mitigated", version=item["version"] + 1)
            self.repo.save("risk", item)
            self.event(item["project_id"], "risk.mitigated", identifier, item["version"])
            return item

    def dashboard(self, project_id: str) -> dict:
        with self.repo.atomic():
            return self._snapshot(project_id)

    def _snapshot(self, project_id: str) -> dict:
        project = self.repo.get("project", project_id)
        requirements = self.repo.list("requirement", project_id)
        risks = self.repo.list("risk", project_id)
        return {
            "project": project,
            "requirements": requirements,
            "risks": risks,
            "evidence": self.repo.list("evidence", project_id),
            "gate": evaluate_gate(requirements, risks),
        }

    def release(self, project_id: str, label: str) -> dict:
        self.actor.require("reviewer")
        with self.repo.atomic():
            snapshot = self._snapshot(project_id)
            if not snapshot["gate"]["ready"]:
                raise DomainError("Release blocked: " + "; ".join(snapshot["gate"]["blockers"]))
            for requirement in snapshot["requirements"]:
                self.actor.independent_of(requirement.get("implemented_by"))
            if any(item["label"] == label for item in self.repo.list("release", project_id)):
                raise DomainError("Release label already exists")
            return self.record(
                "release",
                project_id,
                {
                    "label": label,
                    "snapshot": snapshot,
                    "sha256": snapshot_digest(snapshot),
                    "approved_by": self.actor.subject,
                    "source_commits": sorted(
                        {item["implementation_sha"] for item in snapshot["requirements"]}
                    ),
                },
            )
