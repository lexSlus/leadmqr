# base.py
"""
Базовый класс для SQLAlchemy моделей.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех ORM моделей."""
    pass

