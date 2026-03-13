from app.api.routes.auth import router as auth_router
from app.api.routes.user import router as user_router
from app.api.routes.strategy import router as strategy_router
from app.api.routes.trade import router as trade_router

__all__ = ["auth_router", "user_router", "strategy_router", "trade_router"]
