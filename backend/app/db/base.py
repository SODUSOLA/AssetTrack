from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base; models are imported in app.models so Alembic sees them."""
