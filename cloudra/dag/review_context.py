"""Active review context manager for Supervisor adjudication (directed verdicts)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cloudra.persistence.database import ConversationDB

logger = logging.getLogger(__name__)


class ActiveReview(BaseModel):
    """当前活跃的送审项上下文。"""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    kind: Literal["step", "species", "mechanism"]
    target_name: str
    target_id: str
    requester: str = "coordinator"
    details: dict[str, Any] = Field(default_factory=dict)
    basis_fingerprint: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ReviewContextManager:
    """管理 Supervisor 的当前活动审查上下文（单活跃上下文）。"""

    _active_reviews: dict[str, ActiveReview] = {}

    @classmethod
    def set_active_review(
        cls,
        conversation_id: str,
        review: ActiveReview,
        db: ConversationDB | None = None,
    ) -> bool:
        """登记活跃送审上下文；返回 queued review 是否已持久化（唤醒督导的
        回执判据——只在落库成功时才允许通知，空唤醒必须可诊断）。"""
        cls._active_reviews[conversation_id] = review
        if db is None:
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with db.connect() as con:
                con.execute(
                    """
                    INSERT OR REPLACE INTO dag_review_requests(
                        request_id, kind, requester, target_ids, question,
                        supporting_refs, counterevidence_refs, proposal,
                        basis_fingerprint, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, '[]', '[]', ?, ?, 'queued', ?, ?)
                    """,
                    (
                        review.review_id,
                        "evidence" if review.kind in ("step", "species") else "draft",
                        review.requester,
                        json.dumps([review.target_name]),
                        f"Review {review.kind} '{review.target_name}'",
                        json.dumps(review.details),
                        review.basis_fingerprint or "default",
                        review.created_at or now,
                        now,
                    ),
                )
        except Exception as exc:
            logger.warning("Failed persisting review request to db: %s", exc)
            return False
        return True

    @classmethod
    def get_active_review(
        cls,
        conversation_id: str,
        db: ConversationDB | None = None,
    ) -> ActiveReview | None:
        if conversation_id in cls._active_reviews:
            return cls._active_reviews[conversation_id]
        if db is not None:
            try:
                with db.connect() as con:
                    row = con.execute(
                        """
                        SELECT request_id, kind, requester, target_ids, proposal,
                               basis_fingerprint, created_at
                        FROM dag_review_requests
                        WHERE state = 'queued'
                        ORDER BY rowid DESC LIMIT 1
                        """
                    ).fetchone()
                    if row:
                        req_id, kind, requester, target_ids_json, proposal_json, fp, created_at = row
                        target_ids = json.loads(target_ids_json or "[]")
                        target_name = target_ids[0] if target_ids else ""
                        details = json.loads(proposal_json or "{}")
                        review_kind = details.get("element_type", "step" if kind == "evidence" else "mechanism")
                        review = ActiveReview(
                            review_id=req_id,
                            kind=review_kind,
                            target_name=target_name,
                            target_id=target_name,
                            requester=requester,
                            details=details,
                            basis_fingerprint=fp,
                            created_at=created_at,
                        )
                        cls._active_reviews[conversation_id] = review
                        return review
            except Exception as exc:
                logger.warning("Failed querying active review from db: %s", exc)
        return None

    @classmethod
    def clear_active_review(
        cls,
        conversation_id: str,
        db: ConversationDB | None = None,
        request_id: str | None = None,
    ) -> None:
        review = cls._active_reviews.pop(conversation_id, None)
        target_req_id = request_id or (review.review_id if review else None)
        if db is not None and target_req_id:
            try:
                with db.connect() as con:
                    con.execute(
                        "UPDATE dag_review_requests SET state = 'resolved', updated_at = datetime('now') WHERE request_id = ?",
                        (target_req_id,),
                    )
            except Exception as exc:
                logger.warning("Failed marking review request resolved: %s", exc)
