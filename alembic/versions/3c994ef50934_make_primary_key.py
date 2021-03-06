"""Make primary key

Revision ID: 3c994ef50934
Revises: 73b63ad41d3
Create Date: 2017-07-27 10:58:29.747840

"""

# revision identifiers, used by Alembic.
revision = '3c994ef50934'
down_revision = '73b63ad41d3'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('RepositoryApp2languages', u'id')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('RepositoryApp2languages', sa.Column(u'id', mysql.INTEGER(display_width=11), nullable=False))
    ### end Alembic commands ###
