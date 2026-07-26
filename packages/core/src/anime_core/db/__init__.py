"""Database layer: SQLAlchemy 2.0 async ORM + session factory.

Public API:
    Base, AnimeTitle, AnimeChunk, User, QueryHistory, Feedback, EMBEDDING_DIM
    get_engine, get_session_factory, session_scope
"""

from anime_core.db.engine import get_engine, get_session_factory, session_scope
from anime_core.db.models import (
    EMBEDDING_DIM,
    AnimeChunk,
    AnimeTitle,
    Base,
    Feedback,
    QueryHistory,
    User,
)

__all__ = [
    "EMBEDDING_DIM",
    "AnimeChunk",
    "AnimeTitle",
    "Base",
    "Feedback",
    "QueryHistory",
    "User",
    "get_engine",
    "get_session_factory",
    "session_scope",
]
