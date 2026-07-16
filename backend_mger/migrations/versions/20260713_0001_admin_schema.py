"""create administrator schema

Revision ID: 20260713_0001
Revises:
Create Date: 2026-07-13
"""
from alembic import op

from app.models import Base


revision = "20260713_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
