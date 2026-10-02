"""Real HTTP acceptance with independent principals and commit-bound evidence."""

import json
import os
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from app.domain import snapshot_digest, validate_commit


def main():
    base = os.getenv("BASE_URL", "http://127.0.0.1:18140")
    keys = {"engineer": os.environ["ENGINEER_API_KEY"], "reviewer": os.environ["REVIEWER_API_KEY"]}
    commit = validate_commit(
        os.getenv("COMMIT_SHA")
        or os.getenv("GITHUB_SHA")
        or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    )

    def request(path, method="GET", body=None, expected=200, role="engineer"):
        headers = {"Content-Type": "application/json"}
        if role is not None:
            headers["X-API-Key"] = keys[role]
        call = Request(
            base + path,
            method=method,
            headers=headers,
            data=json.dumps(body).encode() if body else None,
        )
        try:
            response = urlopen(call, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            assert response.status == expected, (path, response.status, response.read().decode())
            return json.loads(response.read())

    request("/health/ready")
    request("/api/projects", expected=401, role=None)
    engineer = request("/api/me")
    reviewer = request("/api/me", role="reviewer")
    assert engineer["subject"] != reviewer["subject"]
    project = request(
        "/api/projects",
        "POST",
        {
            "name": "Acceptance workspace " + str(uuid4())[:8],
            "description": "Synthetic validation: identities, commits, evidence and risks.",
            "owner": engineer["subject"],
        },
        201,
    )
    root = f"/api/projects/{project['id']}"
    req = request(
        root + "/requirements",
        "POST",
        {
            "title": "Reject concurrent stale changes",
            "acceptance": "Return HTTP 409 for a change based on an outdated version.",
            "priority": "must",
            "category": "nonfunctional",
        },
        201,
    )
    status_path = f"/api/requirements/{req['id']}/status"
    request(status_path, "PATCH", {"version": 1, "status": "approved"}, 403)
    request(root + "/releases", "POST", {"label": "v1.0.0"}, 409, "reviewer")
    req = request(status_path, "PATCH", {"version": 1, "status": "approved"}, role="reviewer")
    fields = {"version": req["version"], "status": "implemented", "commit_sha": commit}
    request(status_path, "PATCH", fields, 403, "reviewer")
    req = request(status_path, "PATCH", fields)
    request(
        status_path, "PATCH", {"version": 1, "status": "implemented", "commit_sha": commit}, 409
    )
    result = {
        "version": req["version"],
        "test_name": "Stale write rejected",
        "kind": "acceptance",
        "outcome": "passed",
        "commit_sha": commit,
        "reference": "scripts/smoke.py: actual HTTP conflict and role checks",
    }
    evidence_path = f"/api/requirements/{req['id']}/evidence"
    request(evidence_path, "POST", result, 403)
    request(evidence_path, "POST", {**result, "commit_sha": "0" * 40}, 409, "reviewer")
    request(evidence_path, "POST", result, 201, "reviewer")
    risk = request(
        root + "/risks",
        "POST",
        {
            "title": "Loss of delivery records",
            "owner": engineer["subject"],
            "probability": 3,
            "impact": 5,
        },
        201,
    )
    request(root + "/releases", "POST", {"label": "v1.0.0"}, 409, "reviewer")
    request(
        f"/api/risks/{risk['id']}",
        "PATCH",
        {
            "version": 1,
            "mitigation": "Synthetic fixture: reviewed backup and recovery plan.",
        },
    )
    release = request(root + "/releases", "POST", {"label": "v1.0.0"}, 201, "reviewer")
    assert release["sha256"] == snapshot_digest(release["snapshot"])
    assert release["source_commits"] == [commit]
    assert release["approved_by"] == reviewer["subject"]
    assert request(root)["gate"]["coverage_percent"] == 100
    event = request(root + "/audit")[0]
    assert event["action"] == "release.created" and event["actor"] == reviewer["subject"]
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    (artifacts / "smoke-release.json").write_text(json.dumps(release, indent=2), encoding="utf-8")
    print("HTTP acceptance passed: identity, roles, commit binding, conflicts, risks and release.")


if __name__ == "__main__":
    main()
