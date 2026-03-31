import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    pipeline_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_item = relationship("PipelineItem", backref="project_tasks", lazy="select")

    # feature | bug | fix | improvement
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="feature")

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status flow:
    #   draft         → being written / not yet ready
    #   ready         → user marked it ready, build runner should pick it up
    #   in_progress   → build runner is currently executing it
    #   done          → completed successfully
    #   waiting_for_agent → hit a rate limit / usage limit, waiting to retry
    #   paused        → other task in queue hit a rate limit, this is queued behind it
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)

    # low | medium | high
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")

    # What the agent did — appended as it streams
    agent_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When the runner should retry after a rate-limit pause
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ProjectTask title={self.title!r} status={self.status!r}>"
