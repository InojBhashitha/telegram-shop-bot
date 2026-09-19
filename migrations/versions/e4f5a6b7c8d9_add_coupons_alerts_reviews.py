"""add_coupons_alerts_reviews

Revision ID: e4f5a6b7c8d9
Revises: 0920f2b7d74c
Create Date: 2026-09-19 20:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = '0920f2b7d74c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create coupons table
    op.create_table(
        'coupons',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('discount_type', sa.Enum('PERCENTAGE', 'FIXED', name='coupontype'), nullable=False),
        sa.Column('discount_value', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('min_order_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
        sa.Column('max_discount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('current_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expiry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('affiliate_user_id', sa.Integer(), nullable=True),
        sa.Column('affiliate_commission_pct', sa.Numeric(precision=5, scale=2), nullable=False, server_default='0.00'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['affiliate_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_coupons_code'), 'coupons', ['code'], unique=True)

    # 2. Add columns to orders table
    with op.batch_alter_table('orders') as batch_op:
        batch_op.add_column(sa.Column('coupon_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('expiry_warned', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.create_foreign_key('fk_orders_coupon_id', 'coupons', ['coupon_id'], ['id'])

    # 3. Create stock_alerts table
    op.create_table(
        'stock_alerts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stock_alerts_user_id'), 'stock_alerts', ['user_id'], unique=False)
    op.create_index(op.f('ix_stock_alerts_product_id'), 'stock_alerts', ['product_id'], unique=False)
    op.create_index('ix_stock_alert_pending', 'stock_alerts', ['product_id', 'notified_at'], unique=False)

    # 4. Create product_reviews table
    op.create_table(
        'product_reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id')
    )
    op.create_index(op.f('ix_product_reviews_order_id'), 'product_reviews', ['order_id'], unique=True)
    op.create_index(op.f('ix_product_reviews_product_id'), 'product_reviews', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_reviews_user_id'), 'product_reviews', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_product_reviews_user_id'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_product_id'), table_name='product_reviews')
    op.drop_index(op.f('ix_product_reviews_order_id'), table_name='product_reviews')
    op.drop_table('product_reviews')

    op.drop_index('ix_stock_alert_pending', table_name='stock_alerts')
    op.drop_index(op.f('ix_stock_alerts_product_id'), table_name='stock_alerts')
    op.drop_index(op.f('ix_stock_alerts_user_id'), table_name='stock_alerts')
    op.drop_table('stock_alerts')

    with op.batch_alter_table('orders') as batch_op:
        batch_op.drop_constraint('fk_orders_coupon_id', type_='foreignkey')
        batch_op.drop_column('expiry_warned')
        batch_op.drop_column('coupon_id')

    op.drop_index(op.f('ix_coupons_code'), table_name='coupons')
    op.drop_table('coupons')
