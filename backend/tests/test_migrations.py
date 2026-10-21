import os

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from tests.conftest import BACKEND_DIR


def test_models_match_migrations(engine: Engine) -> None:
    """Fails if a model was changed without a matching Alembic migration."""
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.check(config)
