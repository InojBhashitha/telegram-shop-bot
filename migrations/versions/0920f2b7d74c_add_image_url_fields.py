"""add_image_url_fields

Revision ID: 0920f2b7d74c
Revises: 23362017d827
Create Date: 2026-08-30 18:31:36.030688

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0920f2b7d74c'
down_revision: Union[str, Sequence[str], None] = '23362017d827'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('categories', sa.Column('image_url', sa.String(length=500), nullable=True))
    op.add_column('products', sa.Column('image_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('products', 'image_url')
    op.drop_column('categories', 'image_url')
