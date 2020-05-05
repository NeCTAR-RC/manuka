"""rename organisation

Revision ID: 3840b8c7f97d
Revises: e9e502fdd76f
Create Date: 2020-05-05 16:42:22.153798

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '3840b8c7f97d'
down_revision = 'e9e502fdd76f'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('user', 'home_organization',
                    new_column_name='organisation',
                    existing_type=sa.String(250),
                    nullable=True)


def downgrade():
    op.alter_column('user', 'organisation',
                    new_column_name='home_organization',
                    existing_type=sa.String(250),
                    nullable=True)
