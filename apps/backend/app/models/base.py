"""Declarative base shared by every business table."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
