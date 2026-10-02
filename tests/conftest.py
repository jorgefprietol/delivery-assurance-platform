import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TEST_KEY = "integration-test-key-32-characters-minimum"
REVIEWER_KEY = "reviewer-test-key-32-characters-minimum"
COMMIT = "a" * 40
USERS = [
    {"subject": "test-engineer", "role": "engineer", "api_key": TEST_KEY},
    {"subject": "test-reviewer", "role": "reviewer", "api_key": REVIEWER_KEY},
]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "delivery.db"), USERS)) as client:
        client.headers["X-API-Key"] = TEST_KEY
        yield client


@pytest.fixture
def project(client):
    response = client.post(
        "/api/projects",
        json={
            "name": "Payments delivery",
            "description": "Govern payment release quality",
            "owner": "Engineering team",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def requirement(client, project):
    response = client.post(
        f"/api/projects/{project['id']}/requirements",
        json={
            "title": "Reject stale updates",
            "acceptance": "A stale version returns HTTP 409",
        },
    )
    assert response.status_code == 201
    return response.json()


def advance(client, requirement, target):
    response = client.patch(
        f"/api/requirements/{requirement['id']}/status",
        json={
            "version": requirement["version"],
            "status": target,
            **({"commit_sha": COMMIT} if target == "implemented" else {}),
        },
        headers={"X-API-Key": REVIEWER_KEY if target == "approved" else TEST_KEY},
    )
    assert response.status_code == 200
    return response.json()


def implemented(client, requirement):
    return advance(client, advance(client, requirement, "approved"), "implemented")


def evidence(client, requirement, outcome="passed"):
    return client.post(
        f"/api/requirements/{requirement['id']}/evidence",
        json={
            "version": requirement["version"],
            "test_name": "Optimistic lock conflict",
            "kind": "integration",
            "outcome": outcome,
            "reference": "tests/test_delivery.py::test_stale_update",
            "commit_sha": COMMIT,
        },
        headers={"X-API-Key": REVIEWER_KEY},
    )
