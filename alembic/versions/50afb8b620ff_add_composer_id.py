"""Add composer id

Revision ID: 50afb8b620ff
Revises: 3466afd5950f
Create Date: 2013-09-17 23:33:52.878482

"""

# revision identifiers, used by Alembic.
revision = '50afb8b620ff'
down_revision = '3466afd5950f'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('Apps', sa.Column('composer', sa.Unicode(length=50), server_default=u'expert', nullable=False))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('Apps', 'composer')
    ### end Alembic commands ###