# ============================================================
# ★ BACKEND — NUOVO FILE
# Percorso: app/services/one_import_service.py
#
# Servizio dedicato all'import di "ONE Detail Report" (Option Net Explorer).
# Tutta la logica di matching open/close, calcolo PnL e auto-close è isolata
# qui — non passa per gli endpoint /strategies/ e /close-leg condivisi.
#
# v2: algoritmo FIFO matching. Processiamo le transazioni in ordine cronologico
# e per ciascuna decidiamo on-the-fly se è una CHIUSURA (matcha una leg
# opposta già OPEN) o un'APERTURA (nessun matching disponibile). Questo
# gestisce correttamente i roll/aggiustamenti che ONE registra come tx
# intermedie tra apertura e chiusura del trade.
# ============================================================

from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from app.models.strategy import Strategy
from app.models.trade import Trade, TradeStatus, OptionType, Direction
from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.schemas.one_import import (
    OneImportRequest, OneTradeIn, OneTransactionIn,
    OneImportResponse, OneImportResultItem,
)
from app.services.trade_service import TradeService
from app.utils.exceptions import NotFoundException, ForbiddenException


class OneImportService:
    def __init__(self, db: Session):
        self.db = db
        self.strategy_repo = StrategyRepository(db)
        self.account_repo = AccountRepository(db)
        self.trade_service = TradeService(db)

    def import_trades(self, user_id: str, data: OneImportRequest) -> OneImportResponse:
        account = self.account_repo.find_by_id(data.account_id)
        if not account:
            raise NotFoundException("Account")
        if account.user_id != user_id:
            raise ForbiddenException()

        results: list[OneImportResultItem] = []
        for trade_in in data.trades:
            result = self._import_single_trade(
                user_id=user_id,
                account_id=data.account_id,
                contract_multiplier=data.contract_multiplier,
                expired_open_action=data.expired_open_action,
                trade_in=trade_in,
            )
            results.append(result)

        successful = sum(1 for r in results if r.success)
        return OneImportResponse(
            total=len(results),
            successful=successful,
            failed=len(results) - successful,
            results=results,
        )

    def _import_single_trade(
        self,
        user_id: str,
        account_id: str,
        contract_multiplier: int,
        expired_open_action: str,
        trade_in: OneTradeIn,
    ) -> OneImportResultItem:
        warnings: list[str] = []
        try:
            # Ordina tx per data ASC. Manteniamo l'ordine originale come tie-breaker
            # per tx allo stesso istante (es. due leg aperte insieme).
            indexed_txs = list(enumerate(trade_in.transactions))
            sorted_txs = [
                tx for _, tx in sorted(indexed_txs, key=lambda x: (x[1].date, x[0]))
            ]
            if not sorted_txs:
                raise ValueError("Trade senza transazioni")

            # Crea Strategy con created_at = prima tx in ordine cronologico.
            # Fix del bug "Opened oggi" sulla colonna Portfolio.
            earliest_open_dt = sorted_txs[0].date

            next_number = self.strategy_repo.get_next_number(user_id)
            strategy = Strategy(
                user_id=user_id,
                account_id=account_id,
                number=next_number,
                name=trade_in.trade_name or f"Imported #{trade_in.trade_id}",
                ticker=trade_in.underlying,
                contract_multiplier=contract_multiplier,
                status="OPEN",
                realized_pnl=0.0,
                created_at=earliest_open_dt,
                updated_at=earliest_open_dt,
            )
            self.db.add(strategy)
            self.db.flush()

            # Tracker delle leg aperte: id → qty residua.
            # Una leg ha sempre status=OPEN finché remaining > 0; appena
            # remaining va a 0, la marchiamo CLOSED con close_premium dell'ultima tx.
            all_trades: list[Trade] = []
            remaining_qty: dict[str, int] = {}

            # ─── FIFO matching ───
            for tx in sorted_txs:
                tx_dir = Direction.BUY if tx.transaction.lower() == "buy" else Direction.SELL
                opposite_dir = Direction.SELL if tx_dir == Direction.BUY else Direction.BUY
                tx_remaining = tx.qty
                split_count = 0

                while tx_remaining > 0:
                    matching = self._find_open_match(
                        all_trades, remaining_qty,
                        strike=tx.strike,
                        option_type=tx.option_type,
                        direction=opposite_dir,
                    )
                    if not matching:
                        break  # nessun match → tratta il residuo come APERTURA

                    close_qty = min(tx_remaining, remaining_qty[matching.id])
                    split_count += 1
                    pro_rata_comm = (
                        (tx.commission or 0.0) * close_qty / tx.qty
                        if tx.qty else 0.0
                    )
                    self._close_leg(
                        matching=matching,
                        remaining_qty=remaining_qty,
                        close_qty=close_qty,
                        close_premium=tx.price,  # ★ SIGNED — convention ONE
                        close_date=tx.date,
                        close_commission=pro_rata_comm,
                        all_trades=all_trades,
                    )
                    tx_remaining -= close_qty

                # Residuo non chiuso → apertura nuova
                if tx_remaining > 0:
                    open_comm = (
                        (tx.commission or 0.0) * tx_remaining / tx.qty
                        if tx.qty else 0.0
                    )
                    new_trade = Trade(
                        strategy_id=strategy.id,
                        ticker=trade_in.underlying,
                        option_type=tx.option_type,
                        direction=tx_dir,
                        strike=tx.strike,
                        premium=abs(tx.price),  # apertura: prezzo positivo
                        quantity=tx_remaining,
                        expiry=tx.expiry,
                        enabled=True,
                        frozen=True,
                        commission=open_comm,
                        open_date=tx.date,
                        status=TradeStatus.OPEN,
                    )
                    self.db.add(new_trade)
                    self.db.flush()  # serve per avere l'id
                    all_trades.append(new_trade)
                    remaining_qty[new_trade.id] = tx_remaining

                if split_count > 1:
                    warnings.append(
                        f"Close TX {tx.transaction} {tx.option_type.value} "
                        f"strike {tx.strike} qty {tx.qty} splittata su "
                        f"{split_count} leg (commission distribuita pro-rata)"
                    )

            # ─── Auto-close residuo se ONE dice Closed o expired-auto ───
            is_expired_open = (
                trade_in.status == "Open" and self._is_expired(trade_in)
            )
            should_force_close = (
                trade_in.status == "Closed"
                or (is_expired_open and expired_open_action == "close-auto")
            )
            if should_force_close:
                fallback_dt = trade_in.close_date or datetime.now(timezone.utc)
                for t in all_trades:
                    if remaining_qty.get(t.id, 0) > 0 and t.status == TradeStatus.OPEN:
                        # Split partial se necessario
                        if remaining_qty[t.id] < t.quantity:
                            self._split_residual(t, t.quantity - remaining_qty[t.id])
                            t.quantity = remaining_qty[t.id]
                        t.status = TradeStatus.CLOSED
                        t.close_premium = 0.0
                        t.close_date = fallback_dt
                        t.close_commission = 0.0
                        remaining_qty[t.id] = 0
                        warnings.append(
                            f"Leg orfana {t.direction.value} {t.option_type.value} "
                            f"strike {t.strike} chiusa a premio 0 (fallback)"
                        )

            # ─── Earliest expiry / status ───
            open_expiries = [
                t.expiry for t in all_trades
                if t.status == TradeStatus.OPEN and remaining_qty.get(t.id, 0) > 0
            ]
            strategy.earliest_expiry = min(open_expiries) if open_expiries else None
            if not open_expiries and all_trades:
                strategy.status = "CLOSED"

            self.db.flush()
            # Ricalcolo per coerenza con i Trade salvati (utile se in futuro
            # l'utente modifica una leg)
            self.trade_service.recalculate_strategy_pnl(strategy.id)
            self.db.refresh(strategy)

            # ★ Trust ONE: il PnL di ONE è la fonte di verità per il valore
            # mostrato all'utente. Il nostro calcolato può divergere per:
            #  - errori di float precision sulle somme di tanti contratti
            #  - roll/aggiustamenti che il FIFO matching ricostruisce in modo
            #    diverso dalla logica interna di ONE
            # Sovrascriviamo realized_pnl col valore ONE, ma calcoliamo comunque
            # il delta per loggare le divergenze (warning informativo).
            pnl_delta = None
            calculated_pnl = strategy.realized_pnl
            if trade_in.expected_pnl is not None:
                pnl_delta = round(calculated_pnl - trade_in.expected_pnl, 2)
                strategy.realized_pnl = trade_in.expected_pnl  # ★ override
                if abs(pnl_delta) > 0.5:
                    warnings.append(
                        f"PnL ricalcolato diverge da ONE di {pnl_delta:+.2f} "
                        f"(nostro={calculated_pnl:.2f}, ONE={trade_in.expected_pnl:.2f}); "
                        f"usato il valore ONE."
                    )
            self.db.commit()
            self.db.refresh(strategy)

            return OneImportResultItem(
                trade_id=trade_in.trade_id,
                trade_name=trade_in.trade_name,
                success=True,
                strategy_id=strategy.id,
                realized_pnl=strategy.realized_pnl,
                expected_pnl=trade_in.expected_pnl,
                pnl_delta=pnl_delta,
                warnings=warnings,
            )
        except Exception as e:
            self.db.rollback()
            return OneImportResultItem(
                trade_id=trade_in.trade_id,
                trade_name=trade_in.trade_name,
                success=False,
                warnings=warnings,
                error=str(e),
            )

    # ─── Helpers ───
    def _find_open_match(
        self,
        all_trades: list[Trade],
        remaining_qty: dict[str, int],
        strike: float,
        option_type: OptionType,
        direction: Direction,
    ) -> Trade | None:
        """Cerca una leg OPEN con qty residua > 0 matching strike+type+direction."""
        for t in all_trades:
            if (
                t.status == TradeStatus.OPEN
                and t.strike == strike
                and t.option_type == option_type
                and t.direction == direction
                and remaining_qty.get(t.id, 0) > 0
            ):
                return t
        return None

    def _close_leg(
        self,
        matching: Trade,
        remaining_qty: dict[str, int],
        close_qty: int,
        close_premium: float,
        close_date: datetime,
        close_commission: float,
        all_trades: list[Trade],
    ) -> None:
        """Chiude (parzialmente o totalmente) una leg matching."""
        if close_qty < remaining_qty[matching.id]:
            # Partial: crea residual con la qty rimanente OPEN
            residual_qty = remaining_qty[matching.id] - close_qty
            residual = self._split_residual(matching, residual_qty, status=TradeStatus.OPEN)
            matching.quantity = close_qty
            all_trades.append(residual)
            remaining_qty[residual.id] = residual_qty

        matching.status = TradeStatus.CLOSED
        matching.close_premium = close_premium  # SIGNED
        matching.close_date = close_date
        matching.close_commission = close_commission
        remaining_qty[matching.id] = 0

    def _split_residual(
        self, parent: Trade, residual_qty: int, status: TradeStatus = TradeStatus.OPEN,
    ) -> Trade:
        """Crea una Trade residual con qty=residual_qty, copia tutto dal parent."""
        residual = Trade(
            strategy_id=parent.strategy_id,
            parent_trade_id=parent.id,
            ticker=parent.ticker,
            option_type=parent.option_type,
            direction=parent.direction,
            strike=parent.strike,
            premium=parent.premium,
            quantity=residual_qty,
            expiry=parent.expiry,
            enabled=parent.enabled,
            frozen=parent.frozen,
            commission=0.0,  # già pagata sul parent
            open_date=parent.open_date,
            status=status,
        )
        self.db.add(residual)
        self.db.flush()
        return residual

    def _is_expired(self, trade_in: OneTradeIn) -> bool:
        return trade_in.expiration < date.today()
