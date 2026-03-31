import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class LogoSuggestion(Base):
    __tablename__ = "logo_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    pipeline_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_item = relationship("PipelineItem", backref="logo_suggestions", lazy="select")

    concept_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    svg_content: Mapped[str] = mapped_column(Text, nullable=False)

    # {"primary": "#hex", "secondary": "#hex", "accent": "#hex"}
    color_palette: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # minimal | bold | playful | tech | elegant
    style: Mapped[str] = mapped_column(String(32), nullable=False, default="minimal")

    # suggested | chosen | rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="suggested")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<LogoSuggestion concept={self.concept_name!r} status={self.status!r}>"
