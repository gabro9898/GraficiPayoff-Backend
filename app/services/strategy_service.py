# ============================================================
# Percorso: app/services/strategy_service.py
# v13: + Strategy MODEL feature:
#      - create_model: crea strategia con status=MODEL, leg senza prezzi
#      - replace_model_legs: replace totale delle leg (auto-save dal FE)
#      - fill_model: converte MODEL → OPEN con prezzi/greche
#      - get_all_models_by_user: lista MODEL + cleanup on-the-fly scaduti
# v12: + settle_expired_legs (settle parziale leg-by-leg, multi-expiry)
#      + get_strategies_with_expired_legs (lookup per il nuovo auto-settle)
#
#      Mantiene il vecchio settle() invariato per retro-compatibilità.
#      Tutti i metodi continuano a delegare il calcolo del realized_pnl
#      a TradeService.recalculate_strategy_pnl (fonte unica di verità v11).
# ============================================================

from datetime import datetime, date, timezone
from sqlalchemy.orm import Session
from app.models.strategy import Strategy
from app.models.trade import Trade, TradeStatus, OptionType, Direction
from app.models.underlying_position import UnderlyingPosition, UPDirection, UPStatus
from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.repositories.trade_repository import TradeRepository
from app.schemas.strategy import (
    StrategyCreateRequest, StrategyUpdateRequest,
    StrategyAddLegsRequest, StrategyCloseRequest, StrategySettleRequest,
    StrategySettleExpiredLegsRequest,
    StrategyUpdateLegsRequest, StrategyCloseLegRequest,
    StrategyCreateModelRequest, StrategyReplaceModelLegsRequest,
    StrategyFillModelRequest,
)
from app.schemas.underlying_position import (
    UnderlyingPositionCreateRequest, UnderlyingPositionCloseRequest,
)
from app.utils.exceptions import NotFoundException, ForbiddenException
from app.services.trade_service import TradeService


class StrategyService:
    def __init__(self, db: Session):
        self.db = db
        self.strategy_repo = StrategyRepository(db)
        self.account_repo = AccountRepository(db)
        self.trade_repo = TradeRepository(db)
        # v11: usato come fonte unica per ricalcolare realized_pnl
        self.trade_service = TradeService(db)

    def _verify_account_ownership(self, account_id: str, user_id: str) -> None:
        account = self.account_repo.find_by_id(account_id)
        if not account:
            raise NotFoundException("Account")
        if account.user_id != user_id:
            raise ForbiddenException()

    def _recompute_earliest_expiry(self, strategy: Strategy) -> None:
        open_expiries = [
            t.expiry for t in strategy.trades
            if t.status != TradeStatus.CLOSED and t.expiry is not None
        ]
        strategy.earliest_expiry = min(open_expiries) if open_expiries else None

    def get_all_by_user(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_all_by_user_id(user_id)

    def get_all_by_user_with_trades(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_all_by_user_with_trades(user_id)

    def get_all_by_account(self, account_id: str, user_id: str) -> list[Strategy]:
        self._verify_account_ownership(account_id, user_id)
        return self.strategy_repo.find_all_by_account_id(
            account_id, status="OPEN", exclude_expired=True
        )

    def get_by_id(self, strategy_id: str, user_id: str) -> Strategy:
        strategy = self.strategy_repo.find_by_id(strategy_id)
        if not strategy:
            raise NotFoundException("Strategy")
        if strategy.user_id != user_id:
            raise ForbiddenException()
        return strategy

    def get_by_id_with_trades(self, strategy_id: str, user_id: str) -> Strategy:
        strategy = self.strategy_repo.find_by_id_with_trades(strategy_id)
        if not strategy:
            raise NotFoundException("Strategy")
        if strategy.user_id != user_id:
            raise ForbiddenException()
        return strategy

    def get_open_expired(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_open_expired_by_user(user_id)

    # ★ v12: lookup per il nuovo auto-settle parziale
    def get_strategies_with_expired_legs(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_strategies_with_expired_open_legs(user_id)

    def _create_trade_from_leg(self, strategy_id: str, ticker: str, leg) -> Trade:
        return Trade(
            strategy_id=strategy_id,
            ticker=ticker,
            option_type=leg.option_type,
            direction=leg.direction,
            strike=leg.strike,
            premium=leg.premium,
            quantity=leg.quantity,
            expiry=leg.expiry,
            enabled=leg.enabled,
            frozen=True,
            trading_class=getattr(leg, 'trading_class', None),
            commission=getattr(leg, 'commission', 0.0) or 0.0,
            open_date=getattr(leg, 'open_date', None) or datetime.now(timezone.utc),
            delta=leg.delta,
            gamma=leg.gamma,
            theta=leg.theta,
            vega=leg.vega,
            implied_volatility=leg.implied_volatility,
        )

    def create(self, user_id: str, data: StrategyCreateRequest) -> Strategy:
        self._verify_account_ownership(data.account_id, user_id)
        next_number = self.strategy_repo.get_next_number(user_id)
        earliest = None
        if data.legs:
            earliest = min(leg.expiry for leg in data.legs)
        strategy = Strategy(
            user_id=user_id, account_id=data.account_id, number=next_number,
            name=data.name, description=data.description, ticker=data.ticker,
            fill_price=data.fill_price, contract_multiplier=data.contract_multiplier,
            earliest_expiry=earliest, status="OPEN",
            realized_pnl=0.0,
            underlying_expiry=data.underlying_expiry,
        )
        self.db.add(strategy)
        self.db.flush()
        for leg in data.legs:
            trade = self._create_trade_from_leg(strategy.id, data.ticker, leg)
            self.db.add(trade)
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def add_legs(self, strategy_id: str, user_id: str, data: StrategyAddLegsRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        for leg in data.legs:
            trade = self._create_trade_from_leg(strategy.id, strategy.ticker, leg)
            self.db.add(trade)
        self.db.flush()
        new_earliest = min(leg.expiry for leg in data.legs)
        if strategy.earliest_expiry is None or new_earliest < strategy.earliest_expiry:
            strategy.earliest_expiry = new_earliest
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def update_legs(self, strategy_id: str, user_id: str, data: StrategyUpdateLegsRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        trade_map = {t.id: t for t in strategy.trades}
        for leg_update in data.legs:
            trade = trade_map.get(leg_update.trade_id)
            if not trade:
                raise NotFoundException(f"Trade {leg_update.trade_id}")
            if leg_update.enabled is not None: trade.enabled = leg_update.enabled
            if leg_update.premium is not None: trade.premium = leg_update.premium
            if leg_update.implied_volatility is not None: trade.implied_volatility = leg_update.implied_volatility
            if leg_update.delta is not None: trade.delta = leg_update.delta
            if leg_update.gamma is not None: trade.gamma = leg_update.gamma
            if leg_update.theta is not None: trade.theta = leg_update.theta
            if leg_update.vega is not None: trade.vega = leg_update.vega
            # ★ Commissione INCREMENTALE: sommata a quella esistente del trade
            # (es. una leg attivata da disabled paga commissione di esecuzione).
            if leg_update.commission is not None and leg_update.commission > 0:
                trade.commission = (trade.commission or 0.0) + leg_update.commission
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def close_leg(self, strategy_id: str, user_id: str, data: StrategyCloseLegRequest) -> Strategy:
        """
        Chiude una leg (totale o parziale). Dopo lo split/close, ricalcola P&L.
        """
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)

        trade = None
        for t in strategy.trades:
            if t.id == data.trade_id:
                trade = t
                break
        if not trade:
            raise NotFoundException(f"Trade {data.trade_id}")
        if trade.status == TradeStatus.CLOSED:
            raise ForbiddenException()

        qty_to_close = data.quantity_to_close or trade.quantity
        if qty_to_close > trade.quantity:
            raise ForbiddenException()

        is_partial = qty_to_close < trade.quantity

        if is_partial:
            residual_qty = trade.quantity - qty_to_close
            residual = Trade(
                strategy_id=trade.strategy_id,
                parent_trade_id=trade.id,
                ticker=trade.ticker,
                option_type=trade.option_type,
                direction=trade.direction,
                strike=trade.strike,
                premium=trade.premium,
                quantity=residual_qty,
                expiry=trade.expiry,
                enabled=trade.enabled,
                frozen=trade.frozen,
                trading_class=trade.trading_class,
                commission=0.0,  # commissione apertura già pagata dal parent
                open_date=trade.open_date,
                delta=trade.delta,
                gamma=trade.gamma,
                theta=trade.theta,
                vega=trade.vega,
                underlying_price=trade.underlying_price,
                implied_volatility=trade.implied_volatility,
                status=TradeStatus.OPEN,
            )
            self.db.add(residual)
            trade.quantity = qty_to_close

        trade.status = TradeStatus.CLOSED
        trade.close_premium = data.close_premium
        trade.close_date = now
        trade.close_commission = getattr(data, 'close_commission', 0.0) or 0.0

        # ★ Auto-close strategy: se dopo questo close TUTTI i trade e tutti gli
        # underlying sono CLOSED, la strategia non ha più posizioni aperte → la
        # marchiamo CLOSED. Prima il backend lasciava status=OPEN anche dopo
        # aver chiuso l'ultima leg → UI mostrava strategie "fantasma" aperte
        # con expiry "-" (perché _recompute_earliest_expiry guarda solo open).
        all_trades_closed = all(t.status == TradeStatus.CLOSED for t in strategy.trades)
        all_ups_closed = all(up.status == UPStatus.CLOSED for up in strategy.underlying_positions)
        if all_trades_closed and all_ups_closed and (strategy.trades or strategy.underlying_positions):
            strategy.status = "CLOSED"

        self._recompute_earliest_expiry(strategy)
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def add_underlying(self, strategy_id: str, user_id: str, data: UnderlyingPositionCreateRequest) -> Strategy:
        strategy = self.get_by_id(strategy_id, user_id)
        commission = getattr(data, 'commission', 0.0) or 0.0
        position = UnderlyingPosition(
            strategy_id=strategy.id, ticker=strategy.ticker,
            direction=data.direction, quantity=data.quantity,
            entry_price=data.entry_price, multiplier=data.multiplier,
            commission=commission,
            status=UPStatus.OPEN,
        )
        self.db.add(position)
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def close_underlying(self, strategy_id: str, user_id: str, data: UnderlyingPositionCloseRequest) -> Strategy:
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        position = None
        for p in strategy.underlying_positions:
            if p.id == data.position_id:
                position = p
                break
        if not position:
            raise NotFoundException(f"UnderlyingPosition {data.position_id}")
        if position.status == UPStatus.CLOSED:
            raise ForbiddenException()
        position.status = UPStatus.CLOSED
        position.close_price = data.close_price
        position.close_date = now
        position.close_commission = getattr(data, 'close_commission', 0.0) or 0.0
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def close(self, strategy_id: str, user_id: str, data: StrategyCloseRequest) -> Strategy:
        """
        Chiude tutta la strategia (mass close).
        """
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        strategy.status = "CLOSED"

        for trade in strategy.trades:
            if trade.status == TradeStatus.OPEN:
                trade.status = TradeStatus.CLOSED
                trade.close_premium = data.close_premium
                trade.close_date = now

        for pos in strategy.underlying_positions:
            if pos.status == UPStatus.OPEN:
                close_price = data.underlying_close_price if data.underlying_close_price is not None else 0.0
                pos.status = UPStatus.CLOSED
                pos.close_price = close_price
                pos.close_date = now

        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def settle(self, strategy_id: str, user_id: str, data: StrategySettleRequest) -> Strategy:
        """
        Settle 'vecchio stile': UN solo settlement_price applicato a TUTTE le legs OPEN.
        Marca SEMPRE la strategia come CLOSED. Mantenuto per retro-compatibilità.
        """
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        now = datetime.now(timezone.utc)
        sp = data.settlement_price
        strategy.status = "CLOSED"
        strategy.settlement_price = sp

        for trade in strategy.trades:
            if trade.status == TradeStatus.OPEN:
                if trade.option_type == OptionType.CALL:
                    intrinsic = max(0.0, sp - trade.strike)
                else:
                    intrinsic = max(0.0, trade.strike - sp)
                trade.close_premium = intrinsic
                trade.close_date = now
                trade.status = TradeStatus.CLOSED

        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    # ★ v12: settle parziale leg-by-leg
    def settle_expired_legs(
        self, strategy_id: str, user_id: str,
        data: StrategySettleExpiredLegsRequest,
    ) -> Strategy:
        """
        Settle parziale: chiude SOLO le legs OPEN con expiry < today() per cui
        è presente un settlement_price nella mappa `settlements`.

        - settlements: { "YYYY-MM-DD" : underlying_close_price }
        - intrinsic per leg = max(0, sp - strike) per CALL, max(0, strike - sp) per PUT
        - trade.settlement_price viene salvato per-trade (campo v6)
        - se dopo l'operazione restano trade/underlying OPEN → strategia resta OPEN
        - altrimenti → strategia CLOSED
        - realized_pnl ricalcolato da TradeService.recalculate_strategy_pnl
        """
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        today = date.today()
        now = datetime.now(timezone.utc)
        settlements = data.settlements

        settled_count = 0
        skipped_missing_price = 0

        for trade in strategy.trades:
            if trade.status != TradeStatus.OPEN:
                continue
            if trade.expiry >= today:
                # leg ancora attiva, non toccare
                continue

            expiry_key = trade.expiry.isoformat()
            sp = settlements.get(expiry_key)
            if sp is None:
                # Frontend non ci ha mandato il prezzo per questa scadenza:
                # skip silenzioso (la prossima auto-settle ritenterà).
                skipped_missing_price += 1
                continue

            if trade.option_type == OptionType.CALL:
                intrinsic = max(0.0, sp - trade.strike)
            else:
                intrinsic = max(0.0, trade.strike - sp)

            trade.close_premium = intrinsic
            trade.close_date = now
            trade.status = TradeStatus.CLOSED
            trade.settlement_price = sp
            settled_count += 1

        if settled_count == 0:
            # Nulla settled: non sporcare il DB con commit inutili
            print(f"[SettleExpired] {strategy.id}: 0 legs settled, "
                  f"{skipped_missing_price} skipped (missing price)")
            return strategy

        # Se non rimangono né trade né underlying OPEN, chiudi la strategia
        has_open_trades = any(t.status == TradeStatus.OPEN for t in strategy.trades)
        has_open_underlying = any(
            p.status == UPStatus.OPEN for p in strategy.underlying_positions
        )
        if not has_open_trades and not has_open_underlying:
            strategy.status = "CLOSED"

        # Aggiorna earliest_expiry sui trade ancora aperti
        self._recompute_earliest_expiry(strategy)

        self.db.commit()
        # Fonte unica di verità per realized_pnl
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)

        print(f"[SettleExpired] {strategy.id}: {settled_count} legs settled, "
              f"{skipped_missing_price} skipped, strategy.status={strategy.status}")
        return strategy

    def update(self, strategy_id: str, user_id: str, data: StrategyUpdateRequest) -> Strategy:
        """
        v11: aggiorna name/description/fill_price/account_id/contract_multiplier.
        Se viene cambiato account_id, verifica ownership del nuovo account.
        """
        strategy = self.get_by_id(strategy_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        if 'account_id' in update_data and update_data['account_id'] != strategy.account_id:
            self._verify_account_ownership(update_data['account_id'], user_id)
        return self.strategy_repo.update(strategy, update_data)

    def delete(self, strategy_id: str, user_id: str) -> None:
        strategy = self.get_by_id(strategy_id, user_id)
        self.strategy_repo.delete(strategy)

    # ═══════════════════════════════════════════════════════════
    # ★ v13: MODEL feature
    # ═══════════════════════════════════════════════════════════

    def _create_model_trade_from_leg(self, strategy_id: str, ticker: str, leg) -> Trade:
        """Trade dentro una strategia MODEL: senza premium/greche, frozen=False."""
        return Trade(
            strategy_id=strategy_id,
            ticker=ticker,
            option_type=leg.option_type,
            direction=leg.direction,
            strike=leg.strike,
            premium=None,             # ★ MODEL: prezzo non ancora noto
            quantity=leg.quantity,
            expiry=leg.expiry,
            enabled=leg.enabled,
            frozen=False,             # ★ MODEL: modificabile
            trading_class=getattr(leg, 'trading_class', None),
            commission=0.0,
            open_date=datetime.now(timezone.utc),
        )

    def _verify_parent_strategy(self, parent_id: str | None, user_id: str) -> None:
        if not parent_id:
            return
        parent = self.strategy_repo.find_by_id(parent_id)
        if not parent:
            raise NotFoundException(f"Parent strategy {parent_id}")
        if parent.user_id != user_id:
            raise ForbiddenException()
        if parent.status != "OPEN":
            # Solo strategie OPEN possono avere model annidati
            raise ForbiddenException()

    def get_all_models_by_user(self, user_id: str) -> list[Strategy]:
        # Cleanup on-the-fly: cancella MODEL con tutte le leg scadute
        self.strategy_repo.delete_expired_models_by_user(user_id)
        return self.strategy_repo.find_all_models_by_user(user_id)

    def create_model(self, user_id: str, data: StrategyCreateModelRequest) -> Strategy:
        self._verify_account_ownership(data.account_id, user_id)
        self._verify_parent_strategy(data.parent_strategy_id, user_id)

        next_number = self.strategy_repo.get_next_number(user_id)
        earliest = min((leg.expiry for leg in data.legs), default=None)

        strategy = Strategy(
            user_id=user_id, account_id=data.account_id, number=next_number,
            name=data.name, description=data.description, ticker=data.ticker,
            fill_price=None, contract_multiplier=data.contract_multiplier,
            earliest_expiry=earliest, status="MODEL",
            realized_pnl=0.0,
            underlying_expiry=data.underlying_expiry,
            parent_strategy_id=data.parent_strategy_id,
        )
        self.db.add(strategy)
        self.db.flush()
        for leg in data.legs:
            self.db.add(self._create_model_trade_from_leg(strategy.id, data.ticker, leg))
        self.db.commit()
        self.db.refresh(strategy)
        return strategy

    def replace_model_legs(
        self, strategy_id: str, user_id: str,
        data: StrategyReplaceModelLegsRequest,
    ) -> tuple[Strategy, list[str]]:
        """Auto-save: sostituisce TUTTE le leg di un MODEL.
        Ritorna anche la lista degli ID assegnati (in ordine corrispondente a
        data.legs) — il frontend li usa per promuovere le draft locali (ID
        random) a leg "saved-" senza dover ricaricare il MODEL completo."""
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        if strategy.status != "MODEL":
            raise ForbiddenException()

        # Cancella tutti i trade esistenti
        for trade in list(strategy.trades):
            self.db.delete(trade)
        self.db.flush()

        # Crea i nuovi trade dai leg passati e tiene gli ID assegnati in ordine.
        # NOTA: l'id (UUID) viene assegnato da SQLAlchemy al flush, non al
        # db.add() — quindi flush() prima di leggere t.id.
        new_trades = []
        for leg in data.legs:
            t = self._create_model_trade_from_leg(strategy.id, strategy.ticker, leg)
            self.db.add(t)
            new_trades.append(t)
        self.db.flush()
        assigned_ids: list[str] = [t.id for t in new_trades]

        strategy.earliest_expiry = min((leg.expiry for leg in data.legs), default=None)
        self.db.commit()
        self.db.refresh(strategy)
        return strategy, assigned_ids

    def fill_model(
        self, strategy_id: str, user_id: str,
        data: StrategyFillModelRequest,
    ) -> Strategy:
        """Converte un MODEL in strategia OPEN salvando prezzi/greche delle leg."""
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        if strategy.status != "MODEL":
            raise ForbiddenException()

        # Cancella i trade del MODEL (placeholder senza prezzi)
        for trade in list(strategy.trades):
            self.db.delete(trade)
        self.db.flush()

        # Ricrea i trade come fillati (riusa il helper esistente)
        for leg in data.legs:
            self.db.add(self._create_trade_from_leg(strategy.id, strategy.ticker, leg))

        strategy.status = "OPEN"
        strategy.fill_price = data.fill_price
        strategy.earliest_expiry = min(leg.expiry for leg in data.legs)
        # Il model annidato perde il riferimento al parent una volta fillato:
        # diventa una strategia OPEN indipendente.
        strategy.parent_strategy_id = None

        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    # ═══════════════════════════════════════════════════════════
    # ★ v15: PENDING LEGS — vivono nella stessa Strategy con is_pending=True
    # ═══════════════════════════════════════════════════════════

    def _create_pending_trade(self, strategy_id: str, ticker: str, leg) -> Trade:
        """Crea una pending leg (is_pending=True, frozen=False, premium=None)."""
        return Trade(
            strategy_id=strategy_id,
            ticker=ticker,
            option_type=leg.option_type,
            direction=leg.direction,
            strike=leg.strike,
            premium=None,
            quantity=leg.quantity,
            expiry=leg.expiry,
            enabled=getattr(leg, 'enabled', True),
            frozen=False,
            is_pending=True,
            trading_class=getattr(leg, 'trading_class', None),
            commission=0.0,
            open_date=datetime.now(timezone.utc),
        )

    def create_with_pending(
        self, user_id: str, data,
    ) -> Strategy:
        """Crea una nuova strategia OPEN con leg active (frozen=True) + leg
        pending (is_pending=True) nella stessa Strategy."""
        self._verify_account_ownership(data.account_id, user_id)
        next_number = self.strategy_repo.get_next_number(user_id)
        # earliest_expiry SOLO sulle active (le pending non contano)
        active_expiries = [leg.expiry for leg in data.active_legs]
        earliest_active = min(active_expiries) if active_expiries else None
        strategy = Strategy(
            user_id=user_id, account_id=data.account_id, number=next_number,
            name=data.name, description=data.description, ticker=data.ticker,
            fill_price=data.fill_price, contract_multiplier=data.contract_multiplier,
            earliest_expiry=earliest_active, status="OPEN",
            realized_pnl=0.0,
            underlying_expiry=data.underlying_expiry,
        )
        self.db.add(strategy)
        self.db.flush()
        for leg in data.active_legs:
            self.db.add(self._create_trade_from_leg(strategy.id, data.ticker, leg))
        for leg in data.pending_legs:
            self.db.add(self._create_pending_trade(strategy.id, data.ticker, leg))
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def save_legs(
        self, strategy_id: str, user_id: str, data,
    ) -> Strategy:
        """Aggiunge leg a una strategy OPEN: active → frozen Trade, pending →
        is_pending Trade. Tutto nella stessa Strategy."""
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        for leg in data.active_legs:
            self.db.add(self._create_trade_from_leg(strategy.id, strategy.ticker, leg))
        for leg in data.pending_legs:
            self.db.add(self._create_pending_trade(strategy.id, strategy.ticker, leg))
        if data.active_legs:
            active_expiries = [leg.expiry for leg in data.active_legs]
            new_earliest = min(active_expiries)
            if strategy.earliest_expiry is None or new_earliest < strategy.earliest_expiry:
                strategy.earliest_expiry = new_earliest
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def replace_pending_legs(
        self, strategy_id: str, user_id: str, data,
    ) -> tuple[Strategy, list[str]]:
        """★ Auto-save: sostituisce TUTTE le pending leg di una strategia OPEN.
        I trade fillati (is_pending=False, frozen=True) restano intatti.
        Ritorna anche la lista degli ID assegnati (in ordine corrispondente a
        data.legs) — il frontend li usa per promuovere le draft locali
        (id random) a leg "pending-" senza dover ricaricare il trade."""
        strategy = self.get_by_id_with_trades(strategy_id, user_id)

        # Cancella SOLO le pending esistenti — i fillati restano.
        for trade in list(strategy.trades):
            if trade.is_pending:
                self.db.delete(trade)
        self.db.flush()

        # Ricrea le pending dai legs passati, tenendo gli ID assegnati in
        # ordine. NOTA: l'id viene assegnato da SQLAlchemy al flush() — quindi
        # flush prima di leggere t.id.
        new_trades = []
        for leg in data.legs:
            t = self._create_pending_trade(strategy.id, strategy.ticker, leg)
            self.db.add(t)
            new_trades.append(t)
        self.db.flush()
        assigned_ids: list[str] = [t.id for t in new_trades]

        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy, assigned_ids

    def fill_pending_leg(
        self, strategy_id: str, leg_id: str, user_id: str, data,
    ) -> Strategy:
        """Trasforma una pending leg in trade attivo (in-place). Aggiorna
        i campi premium/commission/greche e setta is_pending=False, frozen=True.
        La leg resta nella stessa Strategy: niente spostamenti tra entità."""
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        leg = next((t for t in strategy.trades if t.id == leg_id), None)
        if not leg:
            raise NotFoundException(f"Leg {leg_id}")
        if not leg.is_pending:
            raise ForbiddenException()  # solo le pending possono essere fillate
        leg.is_pending = False
        leg.frozen = True
        leg.enabled = True
        leg.premium = data.premium
        leg.commission = data.commission
        leg.open_date = datetime.now(timezone.utc)
        leg.delta = data.delta
        leg.gamma = data.gamma
        leg.theta = data.theta
        leg.vega = data.vega
        leg.implied_volatility = data.implied_volatility
        # Aggiorna earliest_expiry del parent (ora include questa leg fillata)
        open_expiries = [
            t.expiry for t in strategy.trades
            if not t.is_pending and t.status != TradeStatus.CLOSED and t.expiry is not None
        ]
        strategy.earliest_expiry = min(open_expiries) if open_expiries else None
        self.db.commit()
        self.trade_service.recalculate_strategy_pnl(strategy.id)
        self.db.refresh(strategy)
        return strategy

    def delete_pending_leg(
        self, strategy_id: str, leg_id: str, user_id: str,
    ) -> None:
        """Rimuove una pending leg dalla Strategy."""
        strategy = self.get_by_id_with_trades(strategy_id, user_id)
        leg = next((t for t in strategy.trades if t.id == leg_id), None)
        if not leg:
            raise NotFoundException(f"Leg {leg_id}")
        if not leg.is_pending:
            raise ForbiddenException()  # solo pending possono essere deleted via questo endpoint
        self.db.delete(leg)
        self.db.commit()