from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from ml_dataset import backfill_ml_interactions, ensure_training_interactions_schema
from models import MLTrainingInteraction
from schemas import (
    MLTrainingBackfillResult,
    MLTrainingInteractionsStats,
    MLTrainingInteractionOut,
)

router = APIRouter(prefix="/api/ml-dataset", tags=["ML Dataset"])


@router.get("/samples", response_model=list[MLTrainingInteractionOut])
def list_training_samples(
    placement: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    ensure_training_interactions_schema(db)

    query = db.query(MLTrainingInteraction)
    if placement:
        query = query.filter(MLTrainingInteraction.placement == placement)
    if event_type:
        query = query.filter(MLTrainingInteraction.event_type == event_type)

    return (
        query.order_by(MLTrainingInteraction.created_at.desc(), MLTrainingInteraction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/stats", response_model=MLTrainingInteractionsStats)
def training_dataset_stats(db: Session = Depends(get_db)):
    ensure_training_interactions_schema(db)

    total_events = db.query(func.count(MLTrainingInteraction.id)).scalar() or 0
    unique_products = db.query(func.count(func.distinct(MLTrainingInteraction.product_id))).scalar() or 0
    unique_users = db.query(func.count(func.distinct(MLTrainingInteraction.user_id))).scalar() or 0
    unique_sessions = db.query(func.count(func.distinct(MLTrainingInteraction.session_id))).scalar() or 0

    event_rows = (
        db.query(
            MLTrainingInteraction.event_type,
            func.count(MLTrainingInteraction.id),
        )
        .group_by(MLTrainingInteraction.event_type)
        .all()
    )

    placement_rows = (
        db.query(
            MLTrainingInteraction.placement,
            func.count(MLTrainingInteraction.id),
        )
        .group_by(MLTrainingInteraction.placement)
        .all()
    )

    return MLTrainingInteractionsStats(
        total_events=int(total_events),
        unique_products=int(unique_products),
        unique_users=int(unique_users),
        unique_sessions=int(unique_sessions),
        samples_needed_for_1000=max(0, 1000 - int(total_events)),
        event_types={event_type: int(count) for event_type, count in event_rows},
        placements={placement or "unknown": int(count) for placement, count in placement_rows},
    )


@router.post("/backfill", response_model=MLTrainingBackfillResult)
def backfill_dataset(db: Session = Depends(get_db)):
    stats = backfill_ml_interactions(db)
    return MLTrainingBackfillResult(**stats)