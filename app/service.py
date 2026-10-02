"""Transactional use cases and traceability rules."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domain import DomainError, evaluate_gate, snapshot_digest, transition
from app.ports import Repository


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class DeliveryService:
    def __init__(self, repository: Repository):
        self.repo = repository

    def record(self, kind: str, project_id: str | None, fields: dict) -> dict:
        item = {
            **fields,
            "id": str(uuid4()),
            "project_id": project_id,
            "version": 1,
            "created_at": timestamp(),
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
                "actor": "workspace-operator",
            }
        )

    def project(self, fields: dict) -> dict:
        with self.repo.atomic():
            return self.record("project", None, fields)

    def requirement(self, project_id: str, fields: dict) -> dict:
        with self.repo.atomic():
            self.repo.get("project", project_id)
            return self.record(
                "requirement",
                project_id,
                {
                    **fields,
                    "status": "draft",
                    "revision": 1,
                },
            )

    def risk(self, project_id: str, fields: dict) -> dict:
        with self.repo.atomic():
            self.repo.get("project", project_id)
            return self.record("risk", project_id, {**fields, "status": "open", "mitigation": ""})

    @staticmethod
    def check_version(item: dict, expected: int) -> None:
        if item["version"] != expected:
            raise DomainError("This record changed; reload before saving")

    def advance(self, identifier: str, expected: int, target: str) -> dict:
        with self.repo.atomic():
            item = self.repo.get("requirement", identifier)
            self.check_version(item, expected)
            transition(item["status"], target)
            item.update(status=target, version=item["version"] + 1)
            self.repo.save("requirement", item)
            self.event(item["project_id"], f"requirement.{target}", identifier, item["version"])
            return item

    def revise(self, identifier: str, expected: int, fields: dict) -> dict:
        with self.repo.atomic():
            item = self.repo.get("requirement", identifier)
            self.check_version(item, expected)
            item.update(fields)
            item.update(status="draft", revision=item["revision"] + 1, version=item["version"] + 1)
            self.repo.save("requirement", item)
            self.event(item["project_id"], "requirement.revised", identifier, item["version"])
            return item

    def evidence(self, identifier: str, expected: int, fields: dict) -> dict:
        with self.repo.atomic():
            item = self.repo.get("requirement", identifier)
            self.check_version(item, expected)
            if item["status"] not in {"implemented", "verified"}:
                raise DomainError("Evidence requires an implemented requirement")
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
            )
            self.repo.save("requirement", item)
            self.event(item["project_id"], "requirement.tested", identifier, item["version"])
            return evidence

    def mitigate(self, identifier: str, expected: int, mitigation: str) -> dict:
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
        with self.repo.atomic():
            snapshot = self._snapshot(project_id)
            if not snapshot["gate"]["ready"]:
                raise DomainError("Release blocked: " + "; ".join(snapshot["gate"]["blockers"]))
            if any(item["label"] == label for item in self.repo.list("release", project_id)):
                raise DomainError("Release label already exists")
            return self.record(
                "release",
                project_id,
                {
                    "label": label,
                    "snapshot": snapshot,
                    "sha256": snapshot_digest(snapshot),
                },
            )
