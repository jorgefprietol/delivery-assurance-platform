"""HTTP adapter and hardened static UI."""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain import DomainError
from app.service import DeliveryService
from app.storage import SQLiteRepository, initialize

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
Version = Annotated[int, Field(ge=1)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectInput(Input):
    name: Title
    description: Text
    owner: Title


class RequirementInput(Input):
    title: Title
    acceptance: Text
    priority: Literal["must", "should", "could"] = "must"
    category: Literal["functional", "nonfunctional"] = "functional"


class TransitionInput(Input):
    version: Version
    status: Literal["approved", "implemented"]


class RevisionInput(RequirementInput):
    version: Version


class RiskInput(Input):
    title: Title
    owner: Title
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)


class MitigationInput(Input):
    version: Version
    mitigation: Text


class EvidenceInput(Input):
    version: Version
    test_name: Title
    kind: Literal["unit", "integration", "system", "acceptance"]
    outcome: Literal["passed", "failed"]
    reference: Text


class ReleaseInput(Input):
    label: Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")]


def create_app(database: str | None = None, api_key: str | None = None) -> FastAPI:
    path = database or os.getenv("DATABASE_PATH", "data/delivery.db")
    key = api_key or os.getenv("API_KEY", "")
    if len(key) < 32:
        raise RuntimeError("API_KEY must contain at least 32 characters")

    @asynccontextmanager
    async def lifespan(_app):
        initialize(path)
        yield

    api = FastAPI(
        title="Delivery Assurance API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    def authorized(x_api_key: Annotated[str | None, Header()] = None):
        if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), key.encode()):
            raise DomainError("Valid X-API-Key required", 401)

    def service():
        repo = SQLiteRepository(path)
        try:
            yield DeliveryService(repo)
        finally:
            repo.close()

    Service = Annotated[DeliveryService, Depends(service)]

    @api.middleware("http")
    async def security_headers(request: Request, call_next):
        request_id = str(uuid4())
        response = await call_next(request)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
                "form-action 'self'",
            }
        )
        logging.getLogger("delivery.http").info(
            "%s %s %s %s", request_id, request.method, request.url.path, response.status_code
        )
        return response

    @api.exception_handler(DomainError)
    async def domain_error(_request, error):
        return JSONResponse(status_code=error.status, content={"detail": error.message})

    @api.get("/health/live")
    def live():
        return {"status": "up"}

    @api.get("/health/ready")
    def ready():
        repo = SQLiteRepository(path)
        try:
            repo.list("project")
        finally:
            repo.close()
        return {"status": "ready"}

    auth = [Depends(authorized)]

    @api.get("/api/projects", dependencies=auth)
    def projects(svc: Service):
        return svc.repo.list("project")

    @api.post("/api/projects", status_code=201, dependencies=auth)
    def create_project(body: ProjectInput, svc: Service):
        return svc.project(body.model_dump())

    @api.get("/api/projects/{project_id}", dependencies=auth)
    def dashboard(project_id: UUID, svc: Service):
        return svc.dashboard(str(project_id))

    @api.post("/api/projects/{project_id}/requirements", status_code=201, dependencies=auth)
    def create_requirement(project_id: UUID, body: RequirementInput, svc: Service):
        return svc.requirement(str(project_id), body.model_dump())

    @api.patch("/api/requirements/{identifier}/status", dependencies=auth)
    def update_status(identifier: UUID, body: TransitionInput, svc: Service):
        return svc.advance(str(identifier), body.version, body.status)

    @api.put("/api/requirements/{identifier}", dependencies=auth)
    def revise(identifier: UUID, body: RevisionInput, svc: Service):
        return svc.revise(str(identifier), body.version, body.model_dump(exclude={"version"}))

    @api.post("/api/requirements/{identifier}/evidence", status_code=201, dependencies=auth)
    def evidence(identifier: UUID, body: EvidenceInput, svc: Service):
        return svc.evidence(str(identifier), body.version, body.model_dump(exclude={"version"}))

    @api.post("/api/projects/{project_id}/risks", status_code=201, dependencies=auth)
    def create_risk(project_id: UUID, body: RiskInput, svc: Service):
        return svc.risk(str(project_id), body.model_dump())

    @api.patch("/api/risks/{identifier}", dependencies=auth)
    def mitigate(identifier: UUID, body: MitigationInput, svc: Service):
        return svc.mitigate(str(identifier), body.version, body.mitigation)

    @api.get("/api/projects/{project_id}/audit", dependencies=auth)
    def audit(project_id: UUID, svc: Service):
        svc.repo.get("project", str(project_id))
        return svc.repo.list("audit", str(project_id))

    @api.get("/api/projects/{project_id}/releases", dependencies=auth)
    def releases(project_id: UUID, svc: Service):
        svc.repo.get("project", str(project_id))
        return svc.repo.list("release", str(project_id))

    @api.post("/api/projects/{project_id}/releases", status_code=201, dependencies=auth)
    def release(project_id: UUID, body: ReleaseInput, svc: Service):
        return svc.release(str(project_id), body.label)

    api.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
    return api
