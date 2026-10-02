import sqlite3
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.domain import DomainError, evaluate_gate, snapshot_digest, transition
from app.main import create_app
from app.service import DeliveryService
from app.storage import SQLiteRepository, initialize
from tests.conftest import advance, evidence, implemented


@pytest.mark.parametrize(
    "current,target",
    [
        ("draft", "implemented"),
        ("draft", "verified"),
        ("approved", "verified"),
        ("verified", "approved"),
        ("implemented", "draft"),
    ],
)
def test_illegal_domain_transition(current, target):
    with pytest.raises(DomainError):
        transition(current, target)


@pytest.mark.parametrize("probability,impact,blocked", [(3, 5, True), (2, 5, False), (5, 5, True)])
def test_risk_threshold(probability, impact, blocked):
    result = evaluate_gate(
        [{"id": "r", "status": "verified"}],
        [
            {
                "id": "risk",
                "status": "open",
                "probability": probability,
                "impact": impact,
            }
        ],
    )
    assert result["ready"] is not blocked
    assert result["high_open_risks"] == int(blocked)


def test_authentication(client):
    for key in ["", "wrong", b"\xe9" * 32]:
        response = client.get("/api/projects", headers={"X-API-Key": key})
        assert response.status_code == 401
    del client.headers["X-API-Key"]
    assert client.post("/api/projects", json={}).status_code == 401


def test_short_key_rejected():
    with pytest.raises(RuntimeError, match="32 characters"):
        create_app(api_key="short")


def test_health_and_security_headers(client):
    for path in ["/health/live", "/health/ready", "/", "/app.js", "/style.css", "/openapi.json"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert len(response.headers["x-request-id"]) == 36


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "x", "description": "valid text", "owner": "valid owner"},
        {"name": "valid", "description": "   ", "owner": "valid owner"},
        {"name": "valid", "description": "valid text", "owner": "valid owner", "role": "admin"},
    ],
)
def test_invalid_project_input(client, payload):
    assert client.post("/api/projects", json=payload).status_code == 422


def test_empty_gate(client, project):
    state = client.get(f"/api/projects/{project['id']}").json()
    assert not state["gate"]["ready"]
    assert state["gate"]["coverage_percent"] == 0
    assert (
        client.post(f"/api/projects/{project['id']}/releases", json={"label": "v1"}).status_code
        == 409
    )


def test_complete_delivery_and_snapshot(client, project, requirement):
    req = implemented(client, requirement)
    assert evidence(client, req).status_code == 201
    response = client.post(f"/api/projects/{project['id']}/releases", json={"label": "v1.0.0"})
    assert response.status_code == 201
    release = response.json()
    assert release["sha256"] == snapshot_digest(release["snapshot"])
    assert release["snapshot"]["gate"]["coverage_percent"] == 100
    assert len(release["snapshot"]["evidence"]) == 1
    assert client.get(f"/api/projects/{project['id']}/releases").json()[0] == release
    assert (
        client.post(f"/api/projects/{project['id']}/releases", json={"label": "v1.0.0"}).status_code
        == 409
    )
    audit = client.get(f"/api/projects/{project['id']}/audit").json()
    assert audit[0]["action"] == "release.created"


def test_evidence_requires_implementation(client, requirement):
    assert evidence(client, requirement).status_code == 409
    req = advance(client, requirement, "approved")
    assert evidence(client, req).status_code == 409


def test_failed_retest_blocks_release(client, project, requirement):
    req = implemented(client, requirement)
    assert evidence(client, req).status_code == 201
    req = client.get(f"/api/projects/{project['id']}").json()["requirements"][0]
    assert evidence(client, req, "failed").status_code == 201
    state = client.get(f"/api/projects/{project['id']}").json()
    assert state["requirements"][0]["status"] == "implemented"
    assert not state["gate"]["ready"]


def test_revision_invalidates_evidence_preserves_release(client, project, requirement):
    req = implemented(client, requirement)
    evidence(client, req)
    release = client.post(f"/api/projects/{project['id']}/releases", json={"label": "v1"}).json()
    req = client.get(f"/api/projects/{project['id']}").json()["requirements"][0]
    updated = client.put(
        f"/api/requirements/{req['id']}",
        json={
            "version": req["version"],
            "title": "Updated behavior",
            "acceptance": "New acceptance rule",
            "priority": "must",
            "category": "nonfunctional",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    state = client.get(f"/api/projects/{project['id']}").json()
    assert not state["gate"]["ready"]
    assert state["evidence"][0]["revision"] == 1
    assert client.get(f"/api/projects/{project['id']}/releases").json()[0] == release


def test_stale_update(client, requirement, project):
    advance(client, requirement, "approved")
    count = len(client.get(f"/api/projects/{project['id']}/audit").json())
    response = client.patch(
        f"/api/requirements/{requirement['id']}/status",
        json={
            "version": 1,
            "status": "implemented",
        },
    )
    assert response.status_code == 409
    assert len(client.get(f"/api/projects/{project['id']}/audit").json()) == count


def test_high_risk_mitigation(client, project, requirement):
    evidence(client, implemented(client, requirement))
    risk = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Data loss",
            "owner": "Operations",
            "probability": 3,
            "impact": 5,
        },
    ).json()
    assert not client.get(f"/api/projects/{project['id']}").json()["gate"]["ready"]
    assert (
        client.patch(f"/api/risks/{risk['id']}", json={"version": 1, "mitigation": " "}).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/risks/{risk['id']}",
            json={
                "version": 1,
                "mitigation": "Verified backup restore before release",
            },
        ).status_code
        == 200
    )
    assert client.get(f"/api/projects/{project['id']}").json()["gate"]["ready"]
    assert (
        client.patch(
            f"/api/risks/{risk['id']}",
            json={
                "version": 1,
                "mitigation": "Outdated control",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize("suffix", ["", "/audit", "/releases"])
def test_missing_project(client, suffix):
    assert client.get(f"/api/projects/{uuid4()}{suffix}").status_code == 404


@pytest.mark.parametrize("kind", ["requirements", "risks"])
def test_orphan_rejected(client, kind):
    fields = (
        {"title": "Valid title", "acceptance": "Valid acceptance"}
        if kind == "requirements"
        else {
            "title": "Valid risk",
            "owner": "Owner",
            "probability": 1,
            "impact": 1,
        }
    )
    assert client.post(f"/api/projects/{uuid4()}/{kind}", json=fields).status_code == 404


@pytest.mark.parametrize("field,value", [("probability", 0), ("impact", 6)])
def test_risk_range_validation(client, project, field, value):
    fields = {"title": "Risk title", "owner": "Owner", "probability": 3, "impact": 3, field: value}
    assert client.post(f"/api/projects/{project['id']}/risks", json=fields).status_code == 422


def test_project_isolation(client, project, requirement):
    other = client.post(
        "/api/projects", json={"name": "Other", "description": "Other scope", "owner": "Owner"}
    ).json()
    assert client.get(f"/api/projects/{other['id']}").json()["requirements"] == []
    assert len(client.get("/api/projects").json()) == 2


def test_sqlite_persistence_rollback_and_immutability(tmp_path):
    path = str(tmp_path / "db.sqlite")
    initialize(path)
    repo = SQLiteRepository(path)
    service = DeliveryService(repo)
    project = service.project({"name": "Persisted"})
    with pytest.raises(RuntimeError), repo.atomic():
        service.record("risk", project["id"], {"title": "Must roll back"})
        raise RuntimeError("simulated failure")
    assert repo.list("risk") == []
    assert len(repo.list("audit", project["id"])) == 1
    with pytest.raises(sqlite3.IntegrityError):
        repo.connection.execute("UPDATE audit SET body='{}'")
    with repo.atomic():
        repo.save("release", {"id": "rel", "project_id": project["id"]})
    for query in [
        "UPDATE records SET body='{}' WHERE kind='release'",
        "DELETE FROM records WHERE kind='release'",
        "DELETE FROM audit",
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            repo.connection.execute(query)
    repo.close()
    reopened = SQLiteRepository(path)
    assert reopened.get("project", project["id"])["name"] == "Persisted"
    reopened.close()


def test_concurrent_optimistic_writers(tmp_path):
    path = str(tmp_path / "db.sqlite")
    initialize(path)
    repo = SQLiteRepository(path)
    service = DeliveryService(repo)
    project = service.project({"name": "Concurrent"})
    requirement = service.requirement(project["id"], {"title": "Concurrency"})
    repo.close()

    def writer(_):
        repository = SQLiteRepository(path)
        try:
            DeliveryService(repository).advance(requirement["id"], 1, "approved")
            return 200
        except DomainError as error:
            return error.status
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(writer, range(2))) == [200, 409]


def test_snapshot_digest_order_and_tampering():
    assert snapshot_digest({"a": 1, "b": 2}) == snapshot_digest({"b": 2, "a": 1})
    assert snapshot_digest({"a": 1}) != snapshot_digest({"a": 2})
