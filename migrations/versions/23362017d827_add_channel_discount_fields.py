"""add_channel_discount_fields

Revision ID: 23362017d827
Revises: 003e0f8bb0bc
Create Date: 2026-08-29 11:06:08.185451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23362017d827'
down_revision: Union[str, Sequence[str], None] = '003e0f8bb0bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column('discount_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'))
    op.add_column('users', sa.Column('channel_discount_claimed', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('channel_discount_used', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'channel_discount_used')
    op.drop_column('users', 'channel_discount_claimed')
    op.drop_column('orders', 'discount_amount')
