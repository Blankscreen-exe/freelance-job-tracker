"""add_email_and_ownership_tracking

Revision ID: 1797baf5bc85
Revises: add_user_auth
Create Date: 2026-03-06 15:49:45.936388

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1797baf5bc85'
down_revision = 'add_user_auth'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add email column to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(), nullable=True))
    
    # Add created_by_user_id to jobs table
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_jobs_created_by_user', 'users', ['created_by_user_id'], ['id'])
        batch_op.create_index('ix_jobs_created_by_user_id', ['created_by_user_id'])
    
    # Add created_by_user_id to clients table
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_clients_created_by_user', 'users', ['created_by_user_id'], ['id'])
        batch_op.create_index('ix_clients_created_by_user_id', ['created_by_user_id'])


def downgrade() -> None:
    # Remove created_by_user_id from clients table
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_index('ix_clients_created_by_user_id')
        batch_op.drop_constraint('fk_clients_created_by_user', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')
    
    # Remove created_by_user_id from jobs table
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_created_by_user_id')
        batch_op.drop_constraint('fk_jobs_created_by_user', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')
    
    # Remove email column from users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email')
