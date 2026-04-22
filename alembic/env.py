from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# ★ Import della config e del Base per autodiscovery dei modelli
from app.config import get_settings
from app.database import Base

# ★ Import di tutti i modelli perché Alembic li veda nel metadata
from app.models.user import User  # noqa: F401
from app.models.account import Account  # noqa: F401
from app.models.strategy import Strategy  # noqa: F401
from app.models.trade import Trade  # noqa: F401
from app.models.underlying_position import UnderlyingPosition  # noqa: F401
from app.models.user_preference import UserPreference  # noqa: F401
from app.models.app_setting import AppSetting  # noqa: F401
from app.models.broker_token import BrokerToken  # noqa: F401
from app.models.gex_data import GexData  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# ★ Imposta sqlalchemy.url dinamicamente dal settings (.env)
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()