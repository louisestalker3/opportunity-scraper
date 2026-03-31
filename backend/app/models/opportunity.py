import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    app_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    app_profile = relationship("AppProfile", backref="opportunity", lazy="select")

    # Composite Viability Index (0-100)
    viability_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sub-scores (0-100 each)
    market_demand_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    complaint_severity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    competition_density_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pricing_gap_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    build_complexity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    differentiation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Aggregated mention stats
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    complaint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alternative_seeking_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # AI-generated explanation of viability score (only set for ai_generated opportunities)
    ai_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # User-assigned rank (1–5 stars, null = unranked)
    user_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    last_scored: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<Opportunity id={self.id} score={self.viability_score}>"
