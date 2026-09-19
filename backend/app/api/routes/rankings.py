"""Cross-job ranking: deterministic, advisory, owner-scoped. No provider calls."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.routes.auth import _require_bearer_user
from app.core.db import get_db
from app.models import User
from app.schemas.ranking import RankItem, RankRunList, RankRunRequest, RankRunResponse
from app.services import ranking_service

router = APIRouter(prefix="/rankings", tags=["rankings"])
CurrentUser = Annotated[User, Depends(_require_bearer_user)]
Database = Annotated[Session, Depends(get_db)]


def present(run, stale: bool, items: list | None) -> dict:
    top = max([item["score"] for item in (run.items or [])], default=None)
    return {"id": run.id, "job_count": len(run.items or []), "top_score": top,
            "profile_hash": run.profile_hash, "engine_version": run.engine_version,
            "is_stale": stale, "items": items,
            "created_at": run.created_at, "updated_at": run.updated_at}


@router.post("", response_model=RankRunResponse, status_code=201)
def create_run(body: RankRunRequest, db: Database, current_user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    run = ranking_service.run_ranking(db, owner_id=current_user.id,
                                      job_ids=body.job_ids, include_archived=body.include_archived)
    items = [RankItem.model_validate(item) for item in run.items]
    return present(run, False, items)


@router.get("", response_model=RankRunList)
def list_runs(db: Database, current_user: CurrentUser, response: Response,
              page: Annotated[int, Query(ge=1)] = 1,
              page_size: Annotated[int, Query(ge=1, le=50)] = 10):
    response.headers["Cache-Control"] = "no-store"
    result = ranking_service.list_runs(db, owner_id=current_user.id, page=page, page_size=page_size)
    return {"items": [present(run, ranking_service.is_stale(db, current_user.id, run), None)
                      for run in result["items"]],
            "total": result["total"], "page": page, "page_size": page_size}


@router.get("/{run_id}", response_model=RankRunResponse)
def get_run(run_id: uuid.UUID, db: Database, current_user: CurrentUser, response: Response,
            page: Annotated[int, Query(ge=1)] = 1,
            page_size: Annotated[int, Query(ge=1, le=50)] = 50):
    response.headers["Cache-Control"] = "no-store"
    run = ranking_service.get_run(db, owner_id=current_user.id, run_id=run_id)
    items = [RankItem.model_validate(item) for item in (run.items or [])]
    total = len(items)
    sliced = items[(page - 1) * page_size:page * page_size]
    payload = present(run, ranking_service.is_stale(db, current_user.id, run), sliced)
    payload["job_count"] = total
    return payload


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: uuid.UUID, db: Database, current_user: CurrentUser):
    ranking_service.delete_run(db, owner_id=current_user.id, run_id=run_id)
    return Response(status_code=204)
