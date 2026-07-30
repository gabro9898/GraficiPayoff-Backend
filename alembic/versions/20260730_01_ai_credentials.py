"""Tabella ai_credentials: chiavi dei fornitori IA cifrate a riposo.

Revision ID: a1f0c3d7e9b2
Revises:
Create Date: 2026-07-30

NOTA OPERATIVA — leggila prima di usare questo file.
Questo progetto crea lo schema a runtime con `Base.metadata.create_all()` e le
correzioni leggere di `ensure_schema_columns()` (app/main.py). La cartella
`alembic/versions/` era VUOTA: non esiste una catena di revisioni preesistente,
quindi questa migrazione ha `down_revision = None` ed e la prima della catena.

Di conseguenza:
  - sugli ambienti che avviano l'app normalmente la tabella nasce da
    `create_all` e questa migrazione non serve;
  - sugli ambienti che usano `alembic upgrade head`, `op.create_table` fallirebbe
    se la tabella esistesse gia: per questo il controllo con l'inspector rende
    la migrazione idempotente in entrambe le direzioni.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1f0c3d7e9b2"
down_revision = None
branch_labels = None
depends_on = None

TABLE_NAME = "ai_credentials"


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        # Ciphertext Fernet: la chiave in chiaro non entra mai in questa colonna.
        sa.Column("api_key_enc", sa.Text(), nullable=False),
        # Ultime 4 cifre, solo per riconoscimento visivo lato utente.
        sa.Column("key_hint", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "provider_id", name="uq_user_ai_provider"),
    )
    op.create_index(
        op.f("ix_ai_credentials_user_id"), TABLE_NAME, ["user_id"], unique=False
    )


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return
    op.drop_index(op.f("ix_ai_credentials_user_id"), table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
