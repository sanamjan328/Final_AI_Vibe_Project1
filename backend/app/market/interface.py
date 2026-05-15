from abc import ABC, abstractmethod
from .models import PriceUpdate, DailyBar


class MarketDataSource(ABC):
    """Contract that both MarketSimulator and MassiveClient must satisfy.

    All code outside backend/app/market/ must never import a concrete
    implementation directly — only use this interface (or the factory).
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Start the background loop. Called once at app startup."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task. Called on app shutdown."""
        ...

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Register a new ticker; it will be included in the next poll/tick."""
        ...

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Deregister a ticker. Its cached price remains until overwritten."""
        ...

    @abstractmethod
    async def get_daily_bars(
        self, ticker: str, from_date: str, to_date: str
    ) -> list[DailyBar]:
        """Fetch historical daily OHLCV bars, sorted ascending by date.

        Returns [] for sources that don't support historical data (simulator).
        """
        ...
