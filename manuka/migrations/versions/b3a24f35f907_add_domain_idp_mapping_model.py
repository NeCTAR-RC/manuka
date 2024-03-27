"""Add domain idp mapping model

Revision ID: b3a24f35f907
Revises: 3580676e9c3d
Create Date: 2024-03-18 15:30:38.023324

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3a24f35f907'
down_revision = '3580676e9c3d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('domain_idp_mapping',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('domain_id', sa.String(length=36), nullable=True),
    sa.Column('idp_entity_id', sa.String(length=250), nullable=True),
    sa.Column('last_seen', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idp_entity_id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('domain_idp_mapping')
    # ### end Alembic commands ###