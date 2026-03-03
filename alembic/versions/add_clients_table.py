"""Add clients table and link to jobs

Revision ID: add_clients
Revises: ebec81d2a79e
Create Date: 2026-01-29 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = 'add_clients'
down_revision = 'ebec81d2a79e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if table already exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    if 'clients' not in tables:
        # Create clients table with extensive fields
        op.create_table(
            'clients',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('client_code', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            
            # Source Information
            sa.Column('source', sa.String(), nullable=True),  # Will use JobSource enum values
            sa.Column('source_url', sa.String(), nullable=True),
            sa.Column('source_notes', sa.Text(), nullable=True),
            
            # Primary Contact
            sa.Column('contact_person', sa.String(), nullable=True),
            sa.Column('email', sa.String(), nullable=True),
            sa.Column('phone', sa.String(), nullable=True),
            sa.Column('mobile', sa.String(), nullable=True),
            
            # Additional Contact Methods
            sa.Column('alternative_email', sa.String(), nullable=True),
            sa.Column('alternative_phone', sa.String(), nullable=True),
            sa.Column('telegram', sa.String(), nullable=True),
            sa.Column('whatsapp', sa.String(), nullable=True),
            sa.Column('skype', sa.String(), nullable=True),
            sa.Column('linkedin', sa.String(), nullable=True),
            sa.Column('other_contact', sa.String(), nullable=True),
            
            # Company Information
            sa.Column('company_name', sa.String(), nullable=True),
            sa.Column('company_registration', sa.String(), nullable=True),
            sa.Column('company_website', sa.String(), nullable=True),
            sa.Column('company_email', sa.String(), nullable=True),
            
            # Address Information
            sa.Column('address_line1', sa.String(), nullable=True),
            sa.Column('address_line2', sa.String(), nullable=True),
            sa.Column('city', sa.String(), nullable=True),
            sa.Column('state_province', sa.String(), nullable=True),
            sa.Column('postal_code', sa.String(), nullable=True),
            sa.Column('country', sa.String(), nullable=True),
            sa.Column('timezone', sa.String(), nullable=True),
            sa.Column('address', sa.Text(), nullable=True),  # Legacy field
            
            # Additional Information
            sa.Column('industry', sa.String(), nullable=True),
            sa.Column('company_size', sa.String(), nullable=True),
            sa.Column('preferred_communication', sa.String(), nullable=True),
            sa.Column('working_hours', sa.String(), nullable=True),
            
            # Notes
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('internal_notes', sa.Text(), nullable=True),
            sa.Column('tags', sa.String(), nullable=True),
            
            # Status
            sa.Column('is_archived', sa.Boolean(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=True),
            
            # Timestamps
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('last_contacted', sa.DateTime(), nullable=True),
            
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_clients_id'), 'clients', ['id'], unique=False)
        op.create_index(op.f('ix_clients_client_code'), 'clients', ['client_code'], unique=True)
        op.create_index('ix_clients_source', 'clients', ['source'], unique=False)  # For filtering by source
    
    # Add client_id to jobs table using batch mode for SQLite
    columns = [col['name'] for col in inspector.get_columns('jobs')]
    if 'client_id' not in columns:
        with op.batch_alter_table('jobs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('client_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_jobs_client_id', 'clients', ['client_id'], ['id'])
            batch_op.create_index('ix_jobs_client_id', ['client_id'], unique=False)


def downgrade() -> None:
    # Check if table/column exists before dropping
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    columns = [col['name'] for col in inspector.get_columns('jobs')] if 'jobs' in tables else []
    
    # Remove client_id from jobs using batch mode for SQLite
    if 'client_id' in columns:
        with op.batch_alter_table('jobs', schema=None) as batch_op:
            batch_op.drop_index('ix_jobs_client_id')
            batch_op.drop_constraint('fk_jobs_client_id', type_='foreignkey')
            batch_op.drop_column('client_id')
    
    # Drop clients table
    if 'clients' in tables:
        op.drop_index('ix_clients_source', table_name='clients')
        op.drop_index(op.f('ix_clients_client_code'), table_name='clients')
        op.drop_index(op.f('ix_clients_id'), table_name='clients')
        op.drop_table('clients')
