"""Update models to avoid uniqueness errors

Revision ID: 4148c3cb14ad
Revises: 21e927fdf78c
Create Date: 2015-04-24 23:27:26.628208

"""

# revision identifiers, used by Alembic.
revision = '4148c3cb14ad'
down_revision = '21e927fdf78c'

import hashlib
from alembic import op
import sqlalchemy as sa
import sqlalchemy.sql as sql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('TranslationExternalSuggestions', sa.Column('human_key_hash', sa.Unicode(length=36), nullable=True))
    op.create_index(u'ix_TranslationExternalSuggestions_human_key_hash', 'TranslationExternalSuggestions', ['human_key_hash'], unique=False)
    ### end Alembic commands ###

    op.drop_constraint("engine", "TranslationExternalSuggestions", "unique")

    metadata = sa.MetaData()
    ExternalSuggestions = sa.Table('TranslationExternalSuggestions', metadata,
        sa.Column('id', sa.Integer()),
        sa.Column('human_key', sa.Unicode(255)),
        sa.Column('human_key_hash', sa.Unicode(36)),
    )

    existing_suggestions = sql.select([ExternalSuggestions.c.id, ExternalSuggestions.c.human_key])
    
    for row in op.get_bind().execute(existing_suggestions):
        suggestion_id = row[ExternalSuggestions.c.id]
        human_key_hash = hashlib.md5(row[ExternalSuggestions.c.human_key]).hexdigest()
        update_stmt = ExternalSuggestions.update().where(ExternalSuggestions.c.id == suggestion_id).values(human_key_hash = human_key_hash)
        op.execute(update_stmt)



def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(u'ix_TranslationExternalSuggestions_human_key_hash', table_name='TranslationExternalSuggestions')
    op.drop_column('TranslationExternalSuggestions', 'human_key_hash')
    ### end Alembic commands ###
