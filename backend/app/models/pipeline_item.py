import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class PipelineItem(Base):
    __tablename__ = "pipeline_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opportunity = relationship("Opportunity", backref="pipeline_items", lazy="select")

    # Session-based identification (no auth yet)
    user_session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_plan: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    # watching | considering | building | dropped
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="watching")

    # Build lifecycle: None | "building" | "built" | "failed"
    build_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    built_repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    build_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Run lifecycle: None | "starting" | "running" | "stopping" | "stopped"
    run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_url: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Chosen identity assets (set after iterating on suggestions)
    chosen_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chosen_logo_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    chosen_logo_colors: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
        return f"<PipelineItem id={self.id} status={self.status!r}>"
