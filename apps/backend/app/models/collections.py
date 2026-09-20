"""SQLAlchemy models for user paper collections."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.chat import Base


class CollectionUserStateRow(Base):
    __tablename__ = 'collection_user_states'

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    initialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))


class CollectionFolderRow(Base):
    __tablename__ = 'collection_folders'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_collection_folders_user_name'),
        Index('idx_collection_folders_user_created', 'user_id', 'created_at', 'id'),
    )


class CollectionItemRow(Base):
    __tablename__ = 'collection_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    folder_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('collection_folders.id', ondelete='CASCADE'), nullable=False,
    )
    paper_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))

    __table_args__ = (
        UniqueConstraint('folder_id', 'paper_id', name='uq_collection_items_folder_paper'),
        Index('idx_collection_items_paper', 'paper_id'),
        Index('idx_collection_items_folder_created', 'folder_id', 'created_at'),
    )