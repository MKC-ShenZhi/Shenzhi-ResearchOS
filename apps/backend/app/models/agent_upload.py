"""Short-lived parsed Agent attachments; original file bytes are never stored."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, text as sql_text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class AgentUploadRow(Base):
    __tablename__ = 'agent_uploads'

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    original_length: Mapped[int] = mapped_column(Integer, nullable=False)
    final_length: Mapped[int] = mapped_column(Integer, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    warning: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sql_text('now()'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index('idx_agent_uploads_owner_expires', 'owner', 'expires_at'),
        Index('idx_agent_uploads_expires', 'expires_at'),
    )
