"""what a new hire starts on: thinking model and image model, chosen by an admin

Revision ID: 0012_hire_models
Revises: 0011_admin_managed
Create Date: 2026-09-22

Bench runs an agent on "Auto" (OpenRouter picks per message) unless a model was
picked, and a picked model always runs. These carry the pick for new hires of a
template; empty means Auto. Kept apart from ``default_model``, which the git
sync rewrites from each spec.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_hire_models"
down_revision: Union[str, Sequence[str], None] = "0011_admin_managed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_templates", sa.Column("hire_model", sa.String(), nullable=False, server_default=""))
    op.add_column("agent_templates", sa.Column("hire_image_model", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("agent_templates", "hire_image_model")
    op.drop_column("agent_templates", "hire_model")
