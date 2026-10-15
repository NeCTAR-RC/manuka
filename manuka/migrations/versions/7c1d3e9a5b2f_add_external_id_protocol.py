#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Add external id protocol

Every external id recorded so far came from a Shibboleth (SAML) login,
so the server default backfills existing rows as 'saml'.

Revision ID: 7c1d3e9a5b2f
Revises: b21c9807518a
Create Date: 2026-10-15 15:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c1d3e9a5b2f'
down_revision = 'b21c9807518a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('external_id', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'protocol',
                sa.String(length=32),
                nullable=False,
                server_default='saml',
            )
        )


def downgrade():
    with op.batch_alter_table('external_id', schema=None) as batch_op:
        batch_op.drop_column('protocol')
