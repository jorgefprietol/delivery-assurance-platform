"""Real HTTP acceptance journey. Creates a synthetic project in the target workspace."""

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.domain import snapshot_digest


def main():
    base = os.getenv("BASE_URL", "http://127.0.0.1:18090")
    key = os.environ["API_KEY"]

    def request(path, method="GET", body=None, expected=200, authorized=True):
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["X-API-Key"] = key
        call = Request(
            base + path,
            method=method,
            headers=headers,
            data=json.dumps(body).encode() if body else None,
        )
        try:
            response = urlopen(call, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            assert response.status == expected, (path, response.status, response.read().decode())
            return json.loads(response.read())

    request("/health/ready")
    request("/api/projects", expected=401, authorized=False)
    project = request(
        "/api/projects",
        "POST",
        {
            "name": "Acceptance workspace " + str(uuid4())[:8],
            "description": "Synthetic delivery validation: evidence, changes and risk controls.",
            "owner": "Engineering operations",
        },
        201,
    )
    root = f"/api/projects/{project['id']}"
    req = request(
        root + "/requirements",
        "POST",
        {
            "title": "Reject concurrent stale changes",
            "acceptance": "Return HTTP 409 when an operator updates an outdated version.",
            "priority": "must",
            "category": "nonfunctional",
        },
        201,
    )
    request(root + "/releases", "POST", {"label": "v1.0.0"}, 409)
    for state in ["approved", "implemented"]:
        req = request(
            f"/api/requirements/{req['id']}/status",
            "PATCH",
            {
                "version": req["version"],
                "status": state,
            },
        )
    request(
        f"/api/requirements/{req['id']}/evidence",
        "POST",
        {
            "version": req["version"],
            "test_name": "Stale write rejected",
            "kind": "acceptance",
            "outcome": "passed",
            "reference": "scripts/smoke.py: real HTTP conflict and release gate assertions",
        },
        201,
    )
    request(
        f"/api/requirements/{req['id']}/status",
        "PATCH",
        {
            "version": 1,
            "status": "implemented",
        },
        409,
    )
    risk = request(
        root + "/risks",
        "POST",
        {
            "title": "Loss of delivery records",
            "owner": "Platform operations",
            "probability": 3,
            "impact": 5,
        },
        201,
    )
    request(root + "/releases", "POST", {"label": "v1.0.0"}, 409)
    request(
        f"/api/risks/{risk['id']}",
        "PATCH",
        {
            "version": 1,
            "mitigation": "Backup and restore procedure documented and exercised by operators.",
        },
    )
    release = request(root + "/releases", "POST", {"label": "v1.0.0"}, 201)
    assert release["sha256"] == snapshot_digest(release["snapshot"])
    assert request(root)["gate"]["coverage_percent"] == 100
    assert request(root + "/audit")[0]["action"] == "release.created"
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    (artifacts / "smoke-release.json").write_text(json.dumps(release, indent=2), encoding="utf-8")
    print(
        "HTTP acceptance passed: auth, transitions, concurrency, evidence, risks, release, audit."
    )


if __name__ == "__main__":
    main()
