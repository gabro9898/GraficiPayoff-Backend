# ============================================================
# Percorso: app/services/trade_service.py
# v3: _recalculate_strategy_pnl include TUTTE le commissioni
#     (apertura+chiusura per trade e underlying). 
#     Esposto come metodo pubblico recalculate_strategy_pnl
#     per essere richiamato dopo modifiche di premium/commission.
# ============================================================

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.trade import Trade, TradeStatus, Direction
from app.repositories.trade_repository import TradeRepository
from app.repositories.strategy_repository import StrategyRepository
from app.schemas.trade import TradeCreateRequest, TradeUpdateRequest, TradeCloseRequest
from app.utils.exceptions import NotFoundException, ForbiddenException


class TradeService:
    def __init__(self, db: Session):
        self.trade_repo = TradeRepository(db)
        self.strategy_repo = StrategyRepository(db)

    def _verify_strategy_ownership(self, strategy_id: str, user_id: str) -> None:
        strategy = self.strategy_repo.find_by_id(strategy_id)
        if not strategy:
            raise NotFoundException("Strategy")
        if strategy.user_id != user_id:
            raise ForbiddenException()

    def _verify_trade_ownership(self, trade_id: str, user_id: str) -> Trade:
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundException("Trade")
        self._verify_strategy_ownership(trade.strategy_id, user_id)
        return trade

    def get_all_by_strategy(self, strategy_id: str, user_id: str) -> list[Trade]:
        self._verify_strategy_ownership(strategy_id, user_id)
        return self.trade_repo.find_all_by_strategy_id(strategy_id)

    def get_by_id(self, trade_id: str, user_id: str) -> Trade:
        return self._verify_trade_ownership(trade_id, user_id)

    def create(self, strategy_id: str, user_id: str, data: TradeCreateRequest) -> Trade:
        self._verify_strategy_ownership(strategy_id, user_id)
        trade = Trade(
            strategy_id=strategy_id,
            **data.model_dump(),
        )
        return self.trade_repo.create(trade)

    def update(self, trade_id: str, user_id: str, data: TradeUpdateRequest) -> Trade:
        """
        Aggiorna un trade. Dopo l'update ricalcola SEMPRE il realized_pnl
        della strategia (così mod. di premium/commission/close_commission/
        close_premium si riflettono immediatamente nel P&L totale).
        """
        trade = self._verify_trade_ownership(trade_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        trade = self.trade_repo.update(trade, update_data)
        # ★ v3: ricalcola sempre, qualsiasi modifica può influire sul P&L
        self.recalculate_strategy_pnl(trade.strategy_id)
        return trade

    def recalculate_strategy_pnl(self, strategy_id: str) -> None:
        """
        ★ v3: Fonte UNICA di verità per realized_pnl.
        Calcola da zero la somma di:
        - P&L lordo delle leg CLOSED (close_premium - premium) × dir × qty × multiplier
        - P&L lordo degli underlying CLOSED
        - − somma di TUTTE le commissioni di apertura (trade + underlying)
        - − somma di TUTTE le commissioni di chiusura dei CLOSED
        Questa funzione può essere chiamata in sicurezza in qualsiasi momento.
        """
        strategy = self.strategy_repo.find_by_id_with_trades(strategy_id)
        if not strategy:
            return

        mult_contract = strategy.contract_multiplier
        total_pnl = 0.0

        # P&L lordo + commissioni dei trade
        for t in strategy.trades:
            # Commissioni di apertura: pagate sempre, anche se la leg è ancora OPEN
            total_pnl -= (t.commission or 0.0)
            # P&L + commissione di chiusura solo se CLOSED
            if t.status == TradeStatus.CLOSED and t.close_premium is not None:
                multiplier = 1 if t.direction == Direction.BUY else -1
                total_pnl += (t.close_premium - t.premium) * multiplier * t.quantity * mult_contract
                total_pnl -= (t.close_commission or 0.0)

        # P&L lordo + commissioni degli underlying
        for p in strategy.underlying_positions:
            total_pnl -= (p.commission or 0.0)
            if p.status == 'CLOSED' and p.close_price is not None:
                mult = 1 if p.direction == 'BUY' else -1
                total_pnl += (p.close_price - p.entry_price) * mult * p.quantity * p.multiplier
                total_pnl -= (p.close_commission or 0.0)

        strategy.realized_pnl = total_pnl
        self.trade_repo.db.commit()

    # ★ Mantenuto come alias privato per backward-compat
    def _recalculate_strategy_pnl(self, strategy_id: str) -> None:
        self.recalculate_strategy_pnl(strategy_id)

    def close(self, trade_id: str, user_id: str, data: TradeCloseRequest) -> Trade:
        trade = self._verify_trade_ownership(trade_id, user_id)
        update_data = {
            "status": TradeStatus.CLOSED,
            "close_premium": data.close_premium,
            "close_date": datetime.now(timezone.utc),
        }
        trade = self.trade_repo.update(trade, update_data)
        self.recalculate_strategy_pnl(trade.strategy_id)
        return trade

    def delete(self, trade_id: str, user_id: str) -> None:
        trade = self._verify_trade_ownership(trade_id, user_id)
        strategy_id = trade.strategy_id
        self.trade_repo.delete(trade)
        # ★ v3: ricalcola dopo delete (commissioni perse devono essere riflesse)
        self.recalculate_strategy_pnl(strategy_id)