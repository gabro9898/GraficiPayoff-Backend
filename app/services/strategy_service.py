from sqlalchemy.orm import Session
from app.models.strategy import Strategy
from app.repositories.strategy_repository import StrategyRepository
from app.schemas.strategy import StrategyCreateRequest, StrategyUpdateRequest
from app.utils.exceptions import NotFoundException, ForbiddenException


class StrategyService:
    def __init__(self, db: Session):
        self.strategy_repo = StrategyRepository(db)

    def get_all_by_user(self, user_id: str) -> list[Strategy]:
        return self.strategy_repo.find_all_by_user_id(user_id)

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

    def create(self, user_id: str, data: StrategyCreateRequest) -> Strategy:
        strategy = Strategy(
            user_id=user_id,
            name=data.name,
            description=data.description,
        )
        return self.strategy_repo.create(strategy)

    def update(self, strategy_id: str, user_id: str, data: StrategyUpdateRequest) -> Strategy:
        strategy = self.get_by_id(strategy_id, user_id)
        return self.strategy_repo.update(strategy, data.model_dump(exclude_unset=True))

    def delete(self, strategy_id: str, user_id: str) -> None:
        strategy = self.get_by_id(strategy_id, user_id)
        self.strategy_repo.delete(strategy)
