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
#
"""Add duplicate state

Revision ID: 3580676e9c3d
Revises: 1eb4f4f09e3b
Create Date: 2022-06-20 13:35:02.812429

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "3580676e9c3d"
down_revision = "1eb4f4f09e3b"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE user MODIFY COLUMN state ENUM('new','registered','created','duplicate')"
    )


def downgrade():
    pass
