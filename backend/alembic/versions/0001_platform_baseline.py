"""Create the platform schema from SQLAlchemy metadata.

The repository started without migration revisions. This baseline lets a fresh
production database be initialized with `alembic upgrade head`; future schema
changes should use regular Alembic revisions.
"""
from alembic import op
from app.core.database import Base
import app.models.base  # noqa: F401 - register all mapped models

revision = "0001_platform_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Deliberately do not drop production data from a baseline downgrade.
    pass
