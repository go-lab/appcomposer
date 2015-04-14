"""Add datetime to fastcache

Revision ID: 20860ffde766
Revises: 471e6f7722a7
Create Date: 2015-04-14 07:44:36.507406

"""

# revision identifiers, used by Alembic.
revision = '20860ffde766'
down_revision = '471e6f7722a7'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('TranslationFastCaches', sa.Column('datetime', sa.DateTime(), nullable=True))
    op.create_index(u'ix_TranslationFastCaches_datetime', 'TranslationFastCaches', ['datetime'], unique=False)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(u'ix_TranslationFastCaches_datetime', table_name='TranslationFastCaches')
    op.drop_column('TranslationFastCaches', 'datetime')
    ### end Alembic commands ###
