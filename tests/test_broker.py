"""Tests for framework/broker.py — paper trading broker."""

import threading
from unittest.mock import patch, MagicMock

import pytest

from framework.broker import Broker, INITIAL_CASH
from framework.exceptions import BrokerError


@pytest.fixture
def broker(tmp_path):
    return Broker(db_path=tmp_path / "broker.json")


class TestBrokerAccount:
    def test_initial_account(self, broker):
        """Account starts with $10,000 cash."""
        account = broker.get_account()
        assert account["cash"] == INITIAL_CASH
        assert account["equity"] == INITIAL_CASH
        assert account["pnl"] == 0.0
        assert account["positions_value"] == 0.0

    def test_get_positions_empty(self, broker):
        """Empty list when no positions."""
        assert broker.get_positions() == []


class TestBrokerBuy:
    def test_buy_success(self, broker):
        """Cash decreases, position created."""
        trade = broker.place_trade("AAPL", "buy", 10, price=150.0)
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 10
        assert trade.price == 150.0
        assert trade.total == 1500.0

        account = broker.get_account()
        assert account["cash"] == pytest.approx(INITIAL_CASH - 1500.0)

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"
        assert positions[0]["quantity"] == 10

    def test_buy_insufficient_cash(self, broker):
        """BrokerError raised when not enough cash."""
        with pytest.raises(BrokerError, match="Insufficient cash"):
            broker.place_trade("AAPL", "buy", 1000, price=150.0)

    def test_buy_zero_quantity(self, broker):
        """BrokerError raised for zero quantity."""
        with pytest.raises(BrokerError, match="positive"):
            broker.place_trade("AAPL", "buy", 0, price=150.0)

    def test_multiple_buys_avg_entry(self, broker):
        """Weighted average entry price after multiple buys."""
        broker.place_trade("AAPL", "buy", 10, price=100.0)
        broker.place_trade("AAPL", "buy", 10, price=200.0)

        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["quantity"] == 20
        assert positions[0]["avg_price"] == pytest.approx(150.0)


class TestBrokerSell:
    def test_sell_success(self, broker):
        """Cash increases, position reduced."""
        broker.place_trade("AAPL", "buy", 10, price=150.0)
        trade = broker.place_trade("AAPL", "sell", 5, price=160.0)

        assert trade.side == "sell"
        assert trade.quantity == 5

        account = broker.get_account()
        # Started 10k, bought 10@150 = -1500, sold 5@160 = +800
        expected_cash = INITIAL_CASH - 1500.0 + 800.0
        assert account["cash"] == pytest.approx(expected_cash)

        positions = broker.get_positions()
        assert positions[0]["quantity"] == 5

    def test_sell_insufficient_shares(self, broker):
        """BrokerError raised when not enough shares."""
        broker.place_trade("AAPL", "buy", 5, price=100.0)
        with pytest.raises(BrokerError, match="Insufficient shares"):
            broker.place_trade("AAPL", "sell", 10, price=100.0)

    def test_sell_all_removes_position(self, broker):
        """Full sell removes position entry."""
        broker.place_trade("AAPL", "buy", 10, price=100.0)
        broker.place_trade("AAPL", "sell", 10, price=110.0)

        positions = broker.get_positions()
        assert len(positions) == 0

    def test_partial_sell(self, broker):
        """Position quantity reduced, avg unchanged."""
        broker.place_trade("AAPL", "buy", 10, price=100.0)
        broker.place_trade("AAPL", "sell", 3, price=110.0)

        positions = broker.get_positions()
        assert positions[0]["quantity"] == 7
        assert positions[0]["avg_price"] == pytest.approx(100.0)


class TestBrokerPositions:
    def test_get_positions_with_data(self, broker):
        """Returns all positions."""
        broker.place_trade("AAPL", "buy", 10, price=150.0)
        broker.place_trade("GOOG", "buy", 5, price=100.0)

        positions = broker.get_positions()
        assert len(positions) == 2
        symbols = {p["symbol"] for p in positions}
        assert symbols == {"AAPL", "GOOG"}

    def test_get_account_after_trades(self, broker):
        """Equity = cash + positions value (at avg price)."""
        broker.place_trade("AAPL", "buy", 10, price=100.0)
        account = broker.get_account()
        assert account["cash"] == pytest.approx(9000.0)
        assert account["positions_value"] == pytest.approx(1000.0)
        assert account["equity"] == pytest.approx(10000.0)
        assert account["pnl"] == pytest.approx(0.0)


class TestBrokerTrades:
    def test_get_trades_all(self, broker):
        """Returns all trades newest first."""
        broker.place_trade("AAPL", "buy", 5, price=100.0)
        broker.place_trade("GOOG", "buy", 3, price=200.0)
        broker.place_trade("AAPL", "sell", 2, price=110.0)

        trades = broker.get_trades()
        assert len(trades) == 3
        # Newest first
        assert trades[0]["side"] == "sell"

    def test_get_trades_by_symbol(self, broker):
        """Filtered by symbol."""
        broker.place_trade("AAPL", "buy", 5, price=100.0)
        broker.place_trade("GOOG", "buy", 3, price=200.0)

        trades = broker.get_trades(symbol="AAPL")
        assert len(trades) == 1
        assert trades[0]["symbol"] == "AAPL"


class TestBrokerPrice:
    def test_get_price_without_yfinance(self, broker):
        """BrokerError with install suggestion when yfinance missing."""
        with patch.dict("sys.modules", {"yfinance": None}):
            with pytest.raises(BrokerError, match="yfinance not installed"):
                broker.get_price("AAPL")


class TestBrokerConcurrency:
    def test_concurrent_trades(self, broker):
        """5 threads buying simultaneously — consistent account."""
        errors = []

        def buy(i):
            try:
                broker.place_trade("AAPL", "buy", 1, price=100.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=buy, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        account = broker.get_account()
        assert account["cash"] == pytest.approx(INITIAL_CASH - 500.0)
        positions = broker.get_positions()
        assert positions[0]["quantity"] == 5
