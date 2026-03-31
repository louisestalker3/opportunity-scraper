import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class NameSuggestion(Base):
    __tablename__ = "name_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    pipeline_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_item = relationship("PipelineItem", backref="name_suggestions", lazy="select")

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # suggested | chosen | rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="suggested")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<NameSuggestion name={self.name!r} status={self.status!r}>"
