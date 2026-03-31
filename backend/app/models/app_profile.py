import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AppProfile(Base):
    __tablename__ = "app_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pricing info stored as list of tier dicts: [{name, price, features}]
    pricing_tiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    target_audience: Mapped[str | None] = mapped_column(String(512), nullable=True)
    avg_review_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Summarised pros/cons — list of strings
    pros: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # List of UUID strings referencing other AppProfile ids
    competitor_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # scraped | ai_generated
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="scraped", index=True)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<AppProfile id={self.id} name={self.name!r}>"
