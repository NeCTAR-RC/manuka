"""Add expiry attributes to user

Revision ID: 1eb4f4f09e3b
Revises: 3840b8c7f97d
Create Date: 2021-01-14 16:33:01.302537

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '1eb4f4f09e3b'
down_revision = '3840b8c7f97d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user', sa.Column('expiry_next_step', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('expiry_status', sa.String(length=64), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('user', 'expiry_status')
    op.drop_column('user', 'expiry_next_step')
    # ### end Alembic commands ###
