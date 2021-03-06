"""Add TranslationSyncLogs

Revision ID: 21e927fdf78c
Revises: 44d704928d8c
Create Date: 2015-04-20 23:34:51.724151

"""

# revision identifiers, used by Alembic.
revision = '21e927fdf78c'
down_revision = '44d704928d8c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('TranslationSyncLogs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('start_datetime', sa.DateTime(), nullable=True),
    sa.Column('end_datetime', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(u'ix_TranslationSyncLogs_end_datetime', 'TranslationSyncLogs', ['end_datetime'], unique=False)
    op.create_index(u'ix_TranslationSyncLogs_start_datetime', 'TranslationSyncLogs', ['start_datetime'], unique=False)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(u'ix_TranslationSyncLogs_start_datetime', table_name='TranslationSyncLogs')
    op.drop_index(u'ix_TranslationSyncLogs_end_datetime', table_name='TranslationSyncLogs')
    op.drop_table('TranslationSyncLogs')
    ### end Alembic commands ###
