"""Add user authentication and role system

Revision ID: add_user_auth
Revises: add_clients
Create Date: 2026-01-29 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite
from sqlalchemy import text
import bcrypt


# revision identifiers, used by Alembic.
revision = 'add_user_auth'
down_revision = 'add_clients'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    # Create user_role_assignments table
    op.create_table(
        'user_role_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'WORKER', 'MIDDLEMAN', name='userrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'role', name='uq_user_role')
    )
    op.create_index(op.f('ix_user_role_assignments_id'), 'user_role_assignments', ['id'], unique=False)
    op.create_index(op.f('ix_user_role_assignments_user_id'), 'user_role_assignments', ['user_id'], unique=False)
    
    # Add user_id to workers table
    with op.batch_alter_table('workers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workers_user_id', 'users', ['user_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_workers_user_id'), ['user_id'], unique=True)
    
    # Add user_id to middlemen table (when it exists)
    # This will be added in a later migration when Middleman model is created
    # For now, we'll skip it or add a check:
    try:
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        tables = inspector.get_table_names()
        if 'middlemen' in tables:
            with op.batch_alter_table('middlemen', schema=None) as batch_op:
                batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key('fk_middlemen_user_id', 'users', ['user_id'], ['id'])
                batch_op.create_index(batch_op.f('ix_middlemen_user_id'), ['user_id'], unique=True)
    except:
        # Table doesn't exist yet, will be added in Task 2 migration
        pass
    
    # Create first admin user
    password_hash = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    op.execute(text("""
        INSERT INTO users (username, password_hash, is_active, created_at, updated_at)
        VALUES ('admin', :password_hash, 1, datetime('now'), datetime('now'))
    """).bindparams(password_hash=password_hash))
    
    # Get the admin user ID and assign ADMIN role
    connection = op.get_bind()
    result = connection.execute(text("SELECT id FROM users WHERE username = 'admin'"))
    admin_id = result.fetchone()[0]
    
    op.execute(text("""
        INSERT INTO user_role_assignments (user_id, role, created_at)
        VALUES (:user_id, 'ADMIN', datetime('now'))
    """).bindparams(user_id=admin_id))


def downgrade() -> None:
    # Remove user_id from middlemen table
    try:
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        tables = inspector.get_table_names()
        if 'middlemen' in tables:
            with op.batch_alter_table('middlemen', schema=None) as batch_op:
                batch_op.drop_index(batch_op.f('ix_middlemen_user_id'))
                batch_op.drop_constraint('fk_middlemen_user_id', type_='foreignkey')
                batch_op.drop_column('user_id')
    except:
        pass
    
    # Remove user_id from workers table
    with op.batch_alter_table('workers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workers_user_id'))
        batch_op.drop_constraint('fk_workers_user_id', type_='foreignkey')
        batch_op.drop_column('user_id')
    
    # Drop user_role_assignments table
    op.drop_index(op.f('ix_user_role_assignments_user_id'), table_name='user_role_assignments')
    op.drop_index(op.f('ix_user_role_assignments_id'), table_name='user_role_assignments')
    op.drop_table('user_role_assignments')
    
    # Drop users table
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
