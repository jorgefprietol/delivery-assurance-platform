"""Framework-independent delivery policies."""

from hashlib import sha256
from json import dumps
from re import fullmatch


class DomainError(Exception):
    def __init__(self, message: str, status: int = 409):
        self.message = message
        self.status = status


TRANSITIONS = {"draft": {"approved"}, "approved": {"implemented"}}


def validate_commit(commit: str | None) -> str:
    if not isinstance(commit, str) or not fullmatch(r"[a-f0-9]{40}", commit):
        raise DomainError("A full lowercase 40-character Git commit SHA is required", 422)
    return commit


def transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise DomainError(f"Cannot transition from {current} to {target}")


def evaluate_gate(requirements: list[dict], risks: list[dict]) -> dict:
    blockers = []
    if not requirements:
        blockers.append("At least one requirement is required")
    for requirement in requirements:
        if requirement["status"] != "verified" or not requirement.get("implementation_sha"):
            blockers.append(f"Requirement {requirement['id']} is not verified")
        elif requirement.get("verified_sha") != requirement["implementation_sha"]:
            blockers.append(f"Requirement {requirement['id']} evidence targets another commit")
    for risk in risks:
        if risk["status"] == "open" and risk["probability"] * risk["impact"] >= 15:
            blockers.append(f"High risk {risk['id']} has no recorded mitigation")
    verified = sum(
        item["status"] == "verified"
        and bool(item.get("implementation_sha"))
        and item.get("verified_sha") == item["implementation_sha"]
        for item in requirements
    )
    return {
        "ready": not blockers,
        "blockers": blockers,
        "requirements": len(requirements),
        "verified": verified,
        "coverage_percent": round(100 * verified / len(requirements), 1) if requirements else 0,
        "high_open_risks": sum(
            risk["status"] == "open" and risk["probability"] * risk["impact"] >= 15
            for risk in risks
        ),
    }


def snapshot_digest(snapshot: dict) -> str:
    return sha256(dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
