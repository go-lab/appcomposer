"""Extend url in RepositoryApp

Revision ID: d3f9c4829e4a
Revises: 2f15229eefbd
Create Date: 2017-10-14 20:20:14.174798

"""

# revision identifiers, used by Alembic.
revision = 'd3f9c4829e4a'
down_revision = '2f15229eefbd'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('RepositoryApps', 'url',
               existing_type=mysql.VARCHAR(length=255),
               type_=sa.Unicode(length=1024),
               existing_nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('RepositoryApps', 'url',
               existing_type=sa.Unicode(length=1024),
               type_=mysql.VARCHAR(length=255),
               existing_nullable=False)
    # ### end Alembic commands ###