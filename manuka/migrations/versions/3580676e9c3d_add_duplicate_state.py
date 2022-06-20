"""Add duplicate state

Revision ID: 3580676e9c3d
Revises: 1eb4f4f09e3b
Create Date: 2022-06-20 13:35:02.812429

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3580676e9c3d'
down_revision = '1eb4f4f09e3b'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE user MODIFY COLUMN state ENUM('new','registered','created','duplicate')")


def downgrade():
    pass
