# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/repositories/gex_repository.py
# Repository per la tabella gex_data.
# Include bulk_replace_ticker: swap atomico in transazione
# (delete vecchi + insert nuovi), così se il fetch fallisce
# a metà il DB resta con i dati di ieri (niente buco).
# ============================================================

from datetime import date, datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.gex_data import GexData


class GexRepository:
    def __init__(self, db: Session):
        self.db = db

    # ═══════════════ Letture ═══════════════

    def find_by_ticker_and_expiry(self, ticker: str, expiry: date) -> list[GexData]:
        """Ritorna tutte le righe per un ticker+expiry, ordinate per strike crescente."""
        return (
            self.db.query(GexData)
            .filter(GexData.ticker == ticker, GexData.expiry == expiry)
            .order_by(GexData.strike.asc())
            .all()
        )

    def get_distinct_expiries(self, ticker: str) -> list[date]:
        """Ritorna la lista ordinata delle scadenze disponibili per un ticker."""
        rows = (
            self.db.query(GexData.expiry)
            .filter(GexData.ticker == ticker)
            .distinct()
            .order_by(GexData.expiry.asc())
            .all()
        )
        return [r[0] for r in rows]

    def get_last_fetched_at(self, ticker: str) -> datetime | None:
        """Ritorna il timestamp più recente di fetch per un ticker, None se il ticker non è in DB."""
        result = (
            self.db.query(func.max(GexData.fetched_at))
            .filter(GexData.ticker == ticker)
            .scalar()
        )
        return result

    def count_for_ticker(self, ticker: str) -> int:
        """Conta le righe per un ticker. Se 0 significa che il DB è vuoto per quel ticker."""
        return self.db.query(GexData).filter(GexData.ticker == ticker).count()

    def total_count(self) -> int:
        """Conta tutte le righe della tabella. Serve per capire se è il primo boot."""
        return self.db.query(GexData).count()

    # ═══════════════ Scrittura: swap atomico giornaliero ═══════════════

    def bulk_replace_ticker(self, ticker: str, rows: list[dict]) -> int:
        """
        Sostituisce atomicamente tutti i dati di un ticker.
        In una sola transazione:
          1. Cancella tutti i record esistenti per quel ticker
          2. Inserisce i nuovi record
        Se qualcosa va storto viene fatto rollback e i dati di ieri restano intatti.

        rows: lista di dict con chiavi: ticker, expiry, strike, oi_call, oi_put,
              iv_call, iv_put, fetched_at.

        Ritorna il numero di righe inserite.
        """
        if not rows:
            # Nessun dato da inserire — non cancelliamo nulla per non svuotare inutilmente
            return 0

        try:
            # 1. Cancella tutti i vecchi record per questo ticker
            self.db.query(GexData).filter(GexData.ticker == ticker).delete(synchronize_session=False)

            # 2. Inserisci i nuovi record in bulk
            self.db.bulk_insert_mappings(GexData, rows)

            # 3. Commit unico: se fallisce, rollback automatico
            self.db.commit()
            return len(rows)
        except Exception:
            self.db.rollback()
            raise