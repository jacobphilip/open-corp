"""Paper trading broker — local TinyDB ledger with optional yfinance for prices."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from framework.db import get_db
from framework.exceptions import BrokerError

INITIAL_CASH = 10_000.00


@dataclass
class Trade:
    id: str
    timestamp: str
    symbol: str
    side: str  # "buy" | "sell"
    quantity: float
    price: float
    total: float


class Broker:
    """Paper trading broker backed by TinyDB."""

    def __init__(self, db_path: Path):
        self._db, self._db_lock = get_db(db_path)
        self._trades = self._db.table("trades")
        self._positions = self._db.table("positions")
        self._account = self._db.table("account")
        self._init_account()

    def _init_account(self) -> None:
        """Initialize account with starting cash if empty."""
        with self._db_lock:
            if not self._account.all():
                self._account.insert({
                    "cash": INITIAL_CASH,
                    "initial": INITIAL_CASH,
                })

    def _get_cash(self) -> float:
        """Current cash balance. Caller must hold lock."""
        records = self._account.all()
        return records[0]["cash"] if records else INITIAL_CASH

    def _set_cash(self, amount: float) -> None:
        """Set cash balance. Caller must hold lock."""
        from tinydb import Query
        Q = Query()
        records = self._account.all()
        if records:
            self._account.update({"cash": amount}, doc_ids=[records[0].doc_id])
        else:
            self._account.insert({"cash": amount, "initial": INITIAL_CASH})

    def get_price(self, symbol: str) -> float:
        """Fetch current price via yfinance. Raises BrokerError if unavailable."""
        try:
            import yfinance as yf
        except ImportError:
            raise BrokerError(
                f"yfinance not installed — cannot fetch price for {symbol}",
                suggestion="pip install yfinance",
            )

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if hist.empty:
                raise BrokerError(f"No price data for {symbol}")
            return float(hist["Close"].iloc[-1])
        except BrokerError:
            raise
        except Exception as e:
            raise BrokerError(f"Failed to fetch price for {symbol}: {e}")

    def place_trade(self, symbol: str, side: str, quantity: float,
                    price: float | None = None) -> Trade:
        """Place a paper trade. Validates cash/shares, updates positions."""
        symbol = symbol.upper()
        if quantity <= 0:
            raise BrokerError("Quantity must be positive")
        if side not in ("buy", "sell"):
            raise BrokerError(f"Invalid side '{side}', must be 'buy' or 'sell'")

        if price is None:
            price = self.get_price(symbol)

        total = price * quantity

        with self._db_lock:
            if side == "buy":
                cash = self._get_cash()
                if total > cash:
                    raise BrokerError(
                        f"Insufficient cash: need ${total:.2f}, have ${cash:.2f}",
                    )
                self._set_cash(cash - total)
                self._update_position_buy(symbol, quantity, price)
            else:
                self._update_position_sell(symbol, quantity, price)

            trade = Trade(
                id=uuid.uuid4().hex[:8],
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                total=total,
            )
            self._trades.insert({
                "id": trade.id,
                "timestamp": trade.timestamp,
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.price,
                "total": trade.total,
            })

        return trade

    def _update_position_buy(self, symbol: str, quantity: float, price: float) -> None:
        """Add to position. Caller must hold lock."""
        from tinydb import Query
        Q = Query()
        existing = self._positions.search(Q.symbol == symbol)
        if existing:
            pos = existing[0]
            old_qty = pos["quantity"]
            old_avg = pos["avg_price"]
            new_qty = old_qty + quantity
            new_avg = (old_qty * old_avg + quantity * price) / new_qty
            self._positions.update(
                {"quantity": new_qty, "avg_price": new_avg},
                doc_ids=[pos.doc_id],
            )
        else:
            self._positions.insert({
                "symbol": symbol,
                "quantity": quantity,
                "avg_price": price,
            })

    def _update_position_sell(self, symbol: str, quantity: float, price: float) -> None:
        """Reduce position. Caller must hold lock."""
        from tinydb import Query
        Q = Query()
        existing = self._positions.search(Q.symbol == symbol)
        if not existing:
            raise BrokerError(f"No position in {symbol} to sell")

        pos = existing[0]
        if quantity > pos["quantity"]:
            raise BrokerError(
                f"Insufficient shares: have {pos['quantity']}, trying to sell {quantity}",
            )

        cash = self._get_cash()
        self._set_cash(cash + quantity * price)

        new_qty = pos["quantity"] - quantity
        if new_qty < 1e-9:  # effectively zero
            self._positions.remove(doc_ids=[pos.doc_id])
        else:
            self._positions.update(
                {"quantity": new_qty},
                doc_ids=[pos.doc_id],
            )

    def get_positions(self) -> list[dict]:
        """Return all current positions (no live price lookup)."""
        with self._db_lock:
            return self._positions.all()

    def get_account(self) -> dict:
        """Return account summary: cash, positions value, equity, P&L."""
        with self._db_lock:
            cash = self._get_cash()
            positions = self._positions.all()
            records = self._account.all()
            initial = records[0].get("initial", INITIAL_CASH) if records else INITIAL_CASH

        positions_value = sum(p["quantity"] * p["avg_price"] for p in positions)
        equity = cash + positions_value
        return {
            "cash": cash,
            "positions_value": positions_value,
            "equity": equity,
            "initial": initial,
            "pnl": equity - initial,
        }

    def get_trades(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        """Trade history, newest first. Optionally filtered by symbol."""
        with self._db_lock:
            if symbol:
                from tinydb import Query
                Q = Query()
                trades = self._trades.search(Q.symbol == symbol.upper())
            else:
                trades = self._trades.all()

        trades.sort(key=lambda t: t.get("timestamp", ""), reverse=True)
        return trades[:limit]
