# ============================================================
# ★ BACKEND — FILE AGGIORNATO
# Percorso: app/schemas/strategy.py
# v11: + Strategy MODEL feature:
#      - ModelLegInput (leg senza prezzi/greche)
#      - StrategyCreateModelRequest (crea strategia MODEL)
#      - StrategyReplaceModelLegsRequest (auto-save: replace totale delle leg)
#      - StrategyFillModelRequest (converte MODEL → OPEN con prezzi/greche)
#      - StrategyResponse.parent_strategy_id
# v10: + StrategySettleExpiredLegsRequest (settle parziale leg-by-leg
#      con mappa expiry → settlement_price del sottostante)
# ============================================================

from datetime import datetime, date
from pydantic import BaseModel, Field
from app.models.trade import OptionType, Direction


class StrategyLegInput(BaseModel):
    option_type: OptionType
    direction: Direction
    strike: float = Field(gt=0)
    premium: float = Field(ge=0)
    quantity: int = Field(gt=0)
    expiry: date
    enabled: bool = True
    trading_class: str | None = None
    commission: float = Field(default=0.0, ge=0)
    open_date: datetime | None = None
    # Prezzo del sottostante al momento del fill: serve a piazzare subito il
    # pallino di entrata sul grafico (entryUnderlyingPrice lato frontend).
    underlying_price: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_volatility: float | None = None


# ★ v11: leg per strategie MODEL (no prezzi/greche/commissioni)
class ModelLegInput(BaseModel):
    option_type: OptionType
    direction: Direction
    strike: float = Field(gt=0)
    quantity: int = Field(gt=0)
    expiry: date
    enabled: bool = True
    trading_class: str | None = None


# ★ v11: crea una nuova strategia in stato MODEL
class StrategyCreateModelRequest(BaseModel):
    account_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    ticker: str = Field(min_length=1, max_length=20)
    contract_multiplier: int = Field(default=1, ge=1)
    underlying_expiry: date | None = None
    parent_strategy_id: str | None = None
    legs: list[ModelLegInput] = Field(default_factory=list)


# ★ v11: replace totale delle leg di un MODEL (usato dall'auto-save FE)
class StrategyReplaceModelLegsRequest(BaseModel):
    legs: list[ModelLegInput] = Field(default_factory=list)


# ★ Auto-save delle pending leg di una strategia OPEN. Analogo a
# StrategyReplaceModelLegsRequest ma valido SOLO sulle pending (is_pending=True),
# lasciando intatti i trade fillati (frozen). Usato quando l'utente modifica una
# pending già salvata (es. shift bulk dello strike): il replace evita duplicati.
class StrategyReplacePendingLegsRequest(BaseModel):
    legs: list[ModelLegInput] = Field(default_factory=list)


# ★ Response dei due replace-legs endpoint. Oltre alla strategy aggiornata,
# include la lista degli ID assegnati alle leg appena create (in ordine
# corrispondente alla richiesta). Il frontend la usa per "promuovere" le
# draft locali a leg salvate senza dover ricaricare l'intero trade.


# ★ v11: converte MODEL → OPEN salvando prezzi/greche delle leg
class StrategyFillModelRequest(BaseModel):
    fill_price: float | None = None
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyCreateRequest(BaseModel):
    account_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    ticker: str = Field(min_length=1, max_length=20)
    fill_price: float | None = None
    contract_multiplier: int = Field(default=1, ge=1)
    underlying_expiry: date | None = None
    legs: list[StrategyLegInput] = Field(default_factory=list)


class StrategyAddLegsRequest(BaseModel):
    fill_price: float | None = None
    legs: list[StrategyLegInput] = Field(min_length=1)


class StrategyCloseRequest(BaseModel):
    close_premium: float
    underlying_close_price: float | None = None


class StrategySettleRequest(BaseModel):
    """Settle 'vecchio stile': un solo settlement_price applicato a TUTTE le legs OPEN."""
    settlement_price: float = Field(gt=0)


# ★ v10: settle parziale per scadenza
class StrategySettleExpiredLegsRequest(BaseModel):
    """
    Settle parziale leg-by-leg.
    `settlements` è una mappa { expiry_iso : settlement_price_underlying }
    dove le chiavi sono date in formato ISO 'YYYY-MM-DD'.

    Il backend:
    - chiude solo le legs OPEN con expiry < today() per cui esiste
      una entry nella mappa
    - calcola intrinsic per ogni leg con il prezzo della SUA expiry
    - salva trade.settlement_price per-trade
    - lascia la strategia OPEN se restano legs non scadute
    - chiude la strategia se non rimane nessuna leg/underlying OPEN
    """
    settlements: dict[str, float] = Field(min_length=1)


class StrategyUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    fill_price: float | None = None
    # ★ v9: nuovi campi modificabili dall'EditStrategyModal
    account_id: str | None = None
    contract_multiplier: int | None = Field(None, ge=1)


class StrategyUpdateLegRequest(BaseModel):
    trade_id: str
    enabled: bool | None = None
    premium: float | None = Field(None, ge=0)
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    # ★ Commissione di fill aggiuntiva (incrementale): viene SOMMATA alla
    # commission esistente del trade. Serve quando l'utente attiva una leg
    # precedentemente disabled e paga la commissione di esecuzione.
    commission: float | None = Field(None, ge=0)


class StrategyUpdateLegsRequest(BaseModel):
    fill_price: float | None = None
    legs: list[StrategyUpdateLegRequest] = Field(min_length=1)


class StrategyCloseLegRequest(BaseModel):
    trade_id: str
    close_premium: float = Field(ge=0)
    close_commission: float = Field(default=0.0, ge=0)
    quantity_to_close: int | None = Field(default=None, gt=0)


# ═══════════════════════════════════════════════════════════════════
# ★ v15: PENDING LEGS — leg desiderate ma non eseguite, vivono nella
# stessa Strategy del trade attivo, marcate con Trade.is_pending=True.
#
# Sostituisce il vecchio sistema "MODEL annidato" (status=MODEL +
# parent_strategy_id) che è stato rimosso. Vantaggi:
#  - 1 sola entità (Trade) invece di 2 (Trade + Strategy MODEL)
#  - niente race condition (era un problema del create-on-demand del MODEL)
#  - niente skipping logic / consolidazione duplicati
#
# Quando una pending leg viene "accesa" (fillata) → diventa una normale
# trade leg dentro la stessa Strategy (is_pending=False, frozen=True).
# ═══════════════════════════════════════════════════════════════════

class StrategyCreateRequest2(BaseModel):
    """v15: crea strategia OPEN con leg active (frozen=True) + leg pending
    (is_pending=True) nella stessa Strategy. Sostituisce il vecchio
    StrategyCreateWithPendingRequest che usava un MODEL annidato."""
    account_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    ticker: str = Field(min_length=1, max_length=20)
    fill_price: float | None = None
    contract_multiplier: int = Field(default=1, ge=1)
    underlying_expiry: date | None = None
    active_legs: list[StrategyLegInput] = Field(default_factory=list)
    pending_legs: list[ModelLegInput] = Field(default_factory=list)


class StrategySaveLegsRequest(BaseModel):
    """v15: aggiunge leg a una strategy OPEN esistente. Le active diventano
    Trade frozen, le pending diventano Trade is_pending=True nella stessa
    Strategy. Sostituisce StrategySaveMixedLegsRequest."""
    fill_price: float | None = None
    active_legs: list[StrategyLegInput] = Field(default_factory=list)
    pending_legs: list[ModelLegInput] = Field(default_factory=list)


class StrategyFillPendingLegRequest(BaseModel):
    """v15: fill incrementale di UNA pending leg → diventa frozen Trade
    nella stessa Strategy (in-place, niente spostamenti tra entities)."""
    fill_price: float | None = None
    premium: float = Field(ge=0)
    commission: float = Field(default=0.0, ge=0)
    # Spot al momento del fill: il pallino di entrata si piazza subito al punto giusto.
    underlying_price: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    implied_volatility: float | None = None


# --- Responses ---

class StrategyResponse(BaseModel):
    id: str
    user_id: str
    account_id: str
    number: int
    name: str
    description: str | None
    ticker: str
    fill_price: float | None
    settlement_price: float | None
    status: str
    realized_pnl: float
    contract_multiplier: int
    earliest_expiry: date | None
    underlying_expiry: date | None
    parent_strategy_id: str | None = None  # ★ v11: link a una strategia OPEN per i model annidati
    # ★ v15: count delle pending leg (Trade.is_pending=True) — usato dal
    # frontend per mostrare il badge "+N P" nelle Positions senza dover
    # caricare l'intero StrategyWithTrades.
    pending_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StrategyWithTradesResponse(StrategyResponse):
    # ★ v15: i Trade includono sia le leg fillate (frozen=True) sia le pending
    # (is_pending=True) — il frontend le distingue tramite il flag is_pending
    # del TradeResponse. Rimosso il vecchio campo `nested_model`.
    trades: list["TradeResponse"] = []
    underlying_positions: list["UnderlyingPositionResponse"] = []


# ★ Response dei replace-legs endpoint: strategy aggiornata + ID assegnati alle
# leg appena create (in ordine corrispondente alla richiesta).
class StrategyReplaceLegsResponse(BaseModel):
    strategy: StrategyWithTradesResponse
    assigned_trade_ids: list[str] = Field(default_factory=list)


from app.schemas.trade import TradeResponse  # noqa: E402
from app.schemas.underlying_position import UnderlyingPositionResponse  # noqa: E402

StrategyWithTradesResponse.model_rebuild()
StrategyReplaceLegsResponse.model_rebuild()