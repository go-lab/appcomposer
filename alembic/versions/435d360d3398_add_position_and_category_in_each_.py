"""Add position and category in each message, so as to order the XML

Revision ID: 435d360d3398
Revises: 2a68ba66c32b
Create Date: 2015-05-03 19:00:38.124617

"""

# revision identifiers, used by Alembic.
revision = '435d360d3398'
down_revision = '2a68ba66c32b'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('ActiveTranslationMessages', sa.Column('category', sa.Unicode(length=255), nullable=True))
    op.add_column('ActiveTranslationMessages', sa.Column('position', sa.Integer(), nullable=True))
    op.create_index(u'ix_ActiveTranslationMessages_category', 'ActiveTranslationMessages', ['category'], unique=False)
    op.create_index(u'ix_ActiveTranslationMessages_position', 'ActiveTranslationMessages', ['position'], unique=False)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(u'ix_ActiveTranslationMessages_position', table_name='ActiveTranslationMessages')
    op.drop_index(u'ix_ActiveTranslationMessages_category', table_name='ActiveTranslationMessages')
    op.drop_column('ActiveTranslationMessages', 'position')
    op.drop_column('ActiveTranslationMessages', 'category')
    ### end Alembic commands ###
