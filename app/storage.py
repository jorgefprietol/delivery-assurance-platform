"""SQLite unit of work: mutations, evidence and audit commit together."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.domain import DomainError

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL, id TEXT NOT NULL, project_id TEXT,
    body TEXT NOT NULL CHECK(json_valid(body)), PRIMARY KEY(kind, id)
);
CREATE INDEX IF NOT EXISTS records_project ON records(kind, project_id);
CREATE TABLE IF NOT EXISTS audit (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
    body TEXT NOT NULL CHECK(json_valid(body))
);
CREATE TRIGGER IF NOT EXISTS immutable_release_update BEFORE UPDATE ON records
WHEN OLD.kind = 'release' BEGIN SELECT RAISE(ABORT, 'immutable release'); END;
CREATE TRIGGER IF NOT EXISTS immutable_release_delete BEFORE DELETE ON records
WHEN OLD.kind = 'release' BEGIN SELECT RAISE(ABORT, 'immutable release'); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_update BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS immutable_audit_delete BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT, 'immutable audit'); END;
"""


def initialize(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] < 2:
            rows = connection.execute(
                "SELECT id, project_id, body FROM records WHERE kind='requirement'"
            ).fetchall()
            for identifier, project_id, body in rows:
                item = json.loads(body)
                item.update(
                    status="draft",
                    revision=item["revision"] + 1,
                    version=item["version"] + 1,
                    created_by=item.get("created_by", "legacy-unattributed"),
                    approved_by=None,
                    implemented_by=None,
                    implementation_sha=None,
                    verified_sha=None,
                    verified_by=None,
                )
                connection.execute(
                    "UPDATE records SET body=? WHERE kind='requirement' AND id=?",
                    (json.dumps(item), identifier),
                )
                event = {
                    "id": str(uuid4()),
                    "project_id": project_id,
                    "action": "migration.requirement_reset",
                    "entity_id": identifier,
                    "version": item["version"],
                    "at": datetime.now(UTC).isoformat(),
                    "actor": "system-migration",
                    "role": "system",
                }
                connection.execute(
                    "INSERT INTO audit(project_id,body) VALUES (?,?)",
                    (project_id, json.dumps(event)),
                )
            connection.execute("INSERT INTO schema_version VALUES (2)")


class SQLiteRepository:
    def __init__(self, path: str):
        self.connection = sqlite3.connect(
            path, timeout=10, isolation_level=None, check_same_thread=False
        )
        self.connection.execute("PRAGMA busy_timeout=10000")

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def atomic(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def get(self, kind: str, identifier: str) -> dict:
        row = self.connection.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", (kind, identifier)
        ).fetchone()
        if row is None:
            raise DomainError(f"{kind.capitalize()} not found", 404)
        return json.loads(row[0])

    def list(self, kind: str, project_id: str | None = None) -> list[dict]:
        if kind == "audit":
            rows = self.connection.execute(
                "SELECT body FROM audit WHERE project_id=? ORDER BY sequence DESC", (project_id,)
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT body FROM records WHERE kind=? AND (? IS NULL OR project_id=?) "
                "ORDER BY rowid",
                (kind, project_id, project_id),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save(self, kind: str, record: dict) -> None:
        self.connection.execute(
            "INSERT INTO records VALUES (?, ?, ?, ?) ON CONFLICT(kind,id) DO UPDATE "
            "SET body=excluded.body",
            (kind, record["id"], record.get("project_id"), json.dumps(record)),
        )

    def audit(self, event: dict) -> None:
        self.connection.execute(
            "INSERT INTO audit(project_id,body) VALUES (?,?)",
            (event["project_id"], json.dumps(event)),
        )
