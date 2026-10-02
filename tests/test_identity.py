import copy
import json
import sqlite3

import pytest

from app.auth import Actor, Credentials
from app.domain import DomainError, evaluate_gate, validate_commit
from app.service import DeliveryService
from app.storage import SCHEMA, SQLiteRepository, initialize
from tests.conftest import COMMIT, REVIEWER_KEY, TEST_KEY, USERS, advance, implemented


def test_authenticated_identity_and_untrusted_header(client, project):
    assert client.get("/api/me").json() == {"subject": "test-engineer", "role": "engineer"}
    assert client.get("/api/me", headers={"X-API-Key": REVIEWER_KEY}).json() == {
        "subject": "test-reviewer",
        "role": "reviewer",
    }
    client.headers["X-Actor"] = "spoofed-reviewer"
    client.post(
        f"/api/projects/{project['id']}/requirements",
        json={
            "title": "Audit principal",
            "acceptance": "Record authenticated subject",
        },
    )
    event = client.get(f"/api/projects/{project['id']}/audit").json()[0]
    assert event["actor"] == "test-engineer"
    assert event["role"] == "engineer"


def test_engineer_cannot_approve_verify_or_release(client, project, requirement):
    assert (
        client.patch(
            f"/api/requirements/{requirement['id']}/status",
            json={
                "version": 1,
                "status": "approved",
            },
        ).status_code
        == 403
    )
    req = implemented(client, requirement)
    assert (
        client.post(
            f"/api/requirements/{req['id']}/evidence",
            json={
                "version": req["version"],
                "test_name": "Own test",
                "kind": "unit",
                "outcome": "passed",
                "reference": "Own report",
                "commit_sha": COMMIT,
            },
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/projects/{project['id']}/releases", json={"label": "v1"}).status_code
        == 403
    )


def test_reviewer_cannot_implement_or_modify_scope(client, project, requirement):
    req = advance(client, requirement, "approved")
    client.headers["X-API-Key"] = REVIEWER_KEY
    calls = [
        ("POST", "/api/projects", {"name": "New", "description": "New project", "owner": "Owner"}),
        (
            "POST",
            f"/api/projects/{project['id']}/requirements",
            {
                "title": "Scope",
                "acceptance": "New criteria",
            },
        ),
        (
            "PATCH",
            f"/api/requirements/{req['id']}/status",
            {
                "version": req["version"],
                "status": "implemented",
                "commit_sha": COMMIT,
            },
        ),
        (
            "PUT",
            f"/api/requirements/{req['id']}",
            {
                "version": req["version"],
                "title": "Revised",
                "acceptance": "New acceptance",
            },
        ),
        (
            "POST",
            f"/api/projects/{project['id']}/risks",
            {
                "title": "New risk",
                "owner": "Owner",
                "probability": 1,
                "impact": 2,
            },
        ),
    ]
    for method, path, body in calls:
        assert client.request(method, path, json=body).status_code == 403
    client.headers["X-API-Key"] = TEST_KEY
    risk = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Risk control",
            "owner": "Owner",
            "probability": 3,
            "impact": 5,
        },
    ).json()
    assert (
        client.patch(
            f"/api/risks/{risk['id']}",
            json={
                "version": 1,
                "mitigation": "Review cannot alter control",
            },
            headers={"X-API-Key": REVIEWER_KEY},
        ).status_code
        == 403
    )


def test_commit_is_required_and_evidence_must_match(client, project, requirement):
    req = advance(client, requirement, "approved")
    for sha in [None, "main", "a" * 39, "A" * 40]:
        body = {"version": req["version"], "status": "implemented"}
        if sha is not None:
            body["commit_sha"] = sha
        assert client.patch(f"/api/requirements/{req['id']}/status", json=body).status_code == 422
    req = advance(client, req, "implemented")
    assert req["implementation_sha"] == COMMIT
    evidence = {
        "version": req["version"],
        "test_name": "Commit test",
        "kind": "integration",
        "outcome": "passed",
        "reference": "Commit report",
        "commit_sha": "b" * 40,
    }
    before = len(client.get(f"/api/projects/{project['id']}/audit").json())
    assert (
        client.post(
            f"/api/requirements/{req['id']}/evidence",
            json=evidence,
            headers={"X-API-Key": REVIEWER_KEY},
        ).status_code
        == 409
    )
    state = client.get(f"/api/projects/{project['id']}").json()
    assert state["evidence"] == []
    assert not state["gate"]["ready"]
    assert len(client.get(f"/api/projects/{project['id']}/audit").json()) == before
    evidence["commit_sha"] = COMMIT
    assert (
        client.post(
            f"/api/requirements/{req['id']}/evidence",
            json=evidence,
            headers={"X-API-Key": REVIEWER_KEY},
        ).status_code
        == 201
    )
    release = client.post(
        f"/api/projects/{project['id']}/releases",
        json={"label": "v1"},
        headers={"X-API-Key": REVIEWER_KEY},
    ).json()
    assert release["source_commits"] == [COMMIT]
    assert release["approved_by"] == "test-reviewer"
    req = release["snapshot"]["requirements"][0]
    assert req["implemented_by"] == "test-engineer"
    assert req["verified_by"] == "test-reviewer"
    assert req["verified_sha"] == req["implementation_sha"]


def test_commit_on_approval_rejected(client, requirement):
    assert (
        client.patch(
            f"/api/requirements/{requirement['id']}/status",
            json={
                "version": 1,
                "status": "approved",
                "commit_sha": COMMIT,
            },
            headers={"X-API-Key": REVIEWER_KEY},
        ).status_code
        == 422
    )


def test_commit_gate_detects_tampered_mapping():
    item = {
        "id": "req",
        "status": "verified",
        "implementation_sha": COMMIT,
        "verified_sha": "b" * 40,
    }
    gate = evaluate_gate([item], [])
    assert not gate["ready"] and gate["coverage_percent"] == 0
    item["implementation_sha"] = None
    assert not evaluate_gate([item], [])["ready"]
    with pytest.raises(DomainError):
        validate_commit("main")


@pytest.mark.parametrize(
    "mutation",
    [
        "subject",
        "role",
        "key",
        "duplicate_subject",
        "duplicate_key",
        "same_role",
        "not_object",
    ],
)
def test_invalid_operator_configuration(mutation):
    users = copy.deepcopy(USERS)
    if mutation == "subject":
        users[0]["subject"] = ""
    if mutation == "role":
        users[0]["role"] = "admin"
    if mutation == "key":
        users[0]["api_key"] = "é" * 40
    if mutation == "duplicate_subject":
        users[1]["subject"] = users[0]["subject"]
    if mutation == "duplicate_key":
        users[1]["api_key"] = users[0]["api_key"]
    if mutation == "same_role":
        users[1]["role"] = "engineer"
    if mutation == "not_object":
        users[0] = "invalid"
    with pytest.raises(RuntimeError):
        Credentials(users)


def test_environment_credentials(monkeypatch):
    monkeypatch.setenv("AUTH_USERS", "invalid json")
    with pytest.raises(RuntimeError):
        Credentials()
    monkeypatch.setenv("AUTH_USERS", "[]")
    with pytest.raises(RuntimeError):
        Credentials()
    monkeypatch.setenv("AUTH_USERS", json.dumps(USERS))
    assert Credentials().authenticate(TEST_KEY).subject == "test-engineer"
    monkeypatch.delenv("AUTH_USERS")
    monkeypatch.setenv("ENGINEER_API_KEY", TEST_KEY)
    monkeypatch.setenv("REVIEWER_API_KEY", REVIEWER_KEY)
    assert Credentials().authenticate(TEST_KEY).role == "engineer"


def test_role_change_does_not_allow_self_review(tmp_path):
    path = str(tmp_path / "db.sqlite")
    initialize(path)
    repo = SQLiteRepository(path)
    engineer = DeliveryService(repo, Actor("author", "engineer"))
    reviewer = DeliveryService(repo, Actor("reviewer", "reviewer"))
    project = engineer.project({"name": "Role change"})
    req = engineer.requirement(project["id"], {"title": "Review identity"})
    changed_author = DeliveryService(repo, Actor("author", "reviewer"))
    with pytest.raises(DomainError, match="own implementation"):
        changed_author.advance(req["id"], 1, "approved")
    req = reviewer.advance(req["id"], 1, "approved")
    changed_reviewer = DeliveryService(repo, Actor("reviewer", "engineer"))
    with pytest.raises(DomainError):
        changed_reviewer.advance(req["id"], 2, "implemented", COMMIT)
    req = engineer.advance(req["id"], 2, "implemented", COMMIT)
    result = {"commit_sha": COMMIT, "outcome": "passed"}
    with pytest.raises(DomainError):
        changed_author.evidence(req["id"], 3, result)
    reviewer.evidence(req["id"], 3, result)
    with pytest.raises(DomainError):
        changed_author.release(project["id"], "v1")
    repo.close()


def test_legacy_migration_invalidates_unattributed_verification(tmp_path):
    path = str(tmp_path / "legacy.sqlite")
    original_release = {"id": "release", "project_id": "project", "label": "v0", "snapshot": {}}
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        requirement = {
            "id": "req",
            "project_id": "project",
            "version": 4,
            "revision": 1,
            "status": "verified",
        }
        connection.execute(
            "INSERT INTO records VALUES ('requirement','req','project',?)",
            (json.dumps(requirement),),
        )
        connection.execute(
            "INSERT INTO records VALUES ('release','release','project',?)",
            (json.dumps(original_release),),
        )
    initialize(path)
    initialize(path)
    repo = SQLiteRepository(path)
    migrated = repo.get("requirement", "req")
    assert migrated["status"] == "draft" and migrated["revision"] == 2
    assert migrated["version"] == 5 and migrated["implementation_sha"] is None
    assert repo.get("release", "release") == original_release
    events = repo.list("audit", "project")
    assert len(events) == 1 and events[0]["actor"] == "system-migration"
    repo.close()
