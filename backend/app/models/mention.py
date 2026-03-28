import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Mention(Base):
    __tablename__ = "mentions"

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_mention_source_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    app_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    app_profile = relationship("AppProfile", backref="mentions", lazy="select")

    # Source platform
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # reddit | hackernews | g2 | capterra | trustpilot | twitter

    # ID within the source platform (post id, tweet id, etc.)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")

    # NLP results
    sentiment: Mapped[str] = mapped_column(
        String(16), nullable=False, default="neutral"
    )  # positive | negative | neutral
    signal_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="general"
    )  # complaint | praise | alternative_seeking | pricing_objection | general
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Extracted app names from the content
    app_names_mentioned: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Full raw data from the source (JSON blob)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Mention id={self.id} source={self.source!r} signal={self.signal_type!r}>"
