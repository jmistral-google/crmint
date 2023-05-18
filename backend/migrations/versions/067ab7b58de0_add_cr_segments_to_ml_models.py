# Copyright 2023 Google Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Add conversion rate segments field to ML Models.

Revision ID: 067ab7b58de0
Revises: 8d8b3ebaf528
Create Date: 2023-05-18 15:31:23.805248

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '067ab7b58de0'
down_revision = '8d8b3ebaf528'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conversion_rate_segments', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ml_models', schema=None) as batch_op:
        batch_op.drop_column('conversion_rate_segments')

    # ### end Alembic commands ###
