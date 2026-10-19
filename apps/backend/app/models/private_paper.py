"""User-owned PDF files in the personal library."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, LargeBinary, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class PrivatePaperRow(Base):
    __tablename__ = 'private_papers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    folder_id: Mapped[int] = mapped_column(Integer, ForeignKey('collection_folders.id', ondelete='CASCADE'), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    __table_args__ = (Index('idx_private_papers_user_folder_created', 'user_id', 'folder_id', created_at.desc()),)
