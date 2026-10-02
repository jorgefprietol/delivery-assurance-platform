"""Credential-backed principals; identity never comes from request bodies."""

import json
import os
import re
import secrets
from dataclasses import dataclass

from app.domain import DomainError


@dataclass(frozen=True)
class Actor:
    subject: str
    role: str

    def require(self, role: str) -> None:
        if self.role != role:
            raise DomainError(f"This action requires the {role} role", 403)

    def independent_of(self, subject: str | None) -> None:
        if self.subject == subject:
            raise DomainError("An operator cannot approve or verify their own implementation", 403)


class Credentials:
    def __init__(self, users: list[dict] | None = None):
        if users is None:
            raw = os.getenv("AUTH_USERS")
            try:
                users = (
                    json.loads(raw)
                    if raw
                    else [
                        {
                            "subject": os.getenv("ENGINEER_ID", "jorge-prieto"),
                            "role": "engineer",
                            "api_key": os.getenv("ENGINEER_API_KEY", ""),
                        },
                        {
                            "subject": os.getenv("REVIEWER_ID", "release-reviewer"),
                            "role": "reviewer",
                            "api_key": os.getenv("REVIEWER_API_KEY", ""),
                        },
                    ]
                )
            except (TypeError, ValueError) as error:
                raise RuntimeError("AUTH_USERS must be a JSON array of operators") from error
        if not isinstance(users, list) or not 2 <= len(users) <= 50:
            raise RuntimeError("Configure between 2 and 50 individual operators")
        self.users: list[tuple[bytes, Actor]] = []
        subjects, keys, roles = set(), set(), set()
        for user in users:
            if not isinstance(user, dict):
                raise RuntimeError("Each operator must be an object")
            subject, role, key = user.get("subject"), user.get("role"), user.get("api_key")
            if not isinstance(subject, str) or not re.fullmatch(
                r"[a-z0-9][a-z0-9._-]{2,63}", subject
            ):
                raise RuntimeError("Each operator needs a valid stable subject")
            if not isinstance(role, str) or role not in {"engineer", "reviewer"}:
                raise RuntimeError("Operator role must be engineer or reviewer")
            if not isinstance(key, str) or len(key) < 32 or not key.isascii():
                raise RuntimeError("Each API key must contain at least 32 ASCII characters")
            if subject in subjects or key in keys:
                raise RuntimeError("Operator subjects and credentials must be unique")
            subjects.add(subject)
            keys.add(key)
            roles.add(role)
            self.users.append((key.encode(), Actor(subject, role)))
        if roles != {"engineer", "reviewer"}:
            raise RuntimeError("Configure separate engineer and reviewer operators")

    def authenticate(self, key: str | None) -> Actor:
        if key:
            for stored, actor in self.users:
                if secrets.compare_digest(key.encode(), stored):
                    return actor
        raise DomainError("Valid individual X-API-Key required", 401)
