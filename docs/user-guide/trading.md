# Paper Trading

open-corp includes a paper trading broker for simulating stock trades in AI workflows.

## Account Management

```bash
# View account summary
corp broker account

# View current positions
corp broker positions

# View trade history
corp broker trades
corp broker trades --symbol AAPL --limit 50
```

## Trading

```bash
# Buy shares (with explicit price)
corp broker buy AAPL 10 --price 150

# Sell shares
corp broker sell AAPL 5 --price 160

# Get current price (requires yfinance)
corp broker price AAPL
```

## Live Prices

Install the optional `yfinance` dependency for real-time prices:

```bash
pip install "open-corp[broker]"
```

Without yfinance, you must specify `--price` on every trade.

## Workflow Integration

Use the broker in trading workflows:

```yaml
name: trading-pipeline
description: Analyze and execute trades

nodes:
  analyze:
    worker: trader
    message: "Analyze AAPL for buy/sell signals"

  execute:
    worker: trader
    message: "Based on analysis: {analyze.output} — recommend a trade"
    depends_on: [analyze]
    condition: "contains:buy"
```

## Account Defaults

- Starting cash: $100,000
- All trades are paper (simulated)
- Trade history persisted in `data/broker.json`
- No real money is involved

## Data Storage

The broker stores all state in `data/broker.json`:

- Account balance
- Open positions (symbol, quantity, average price)
- Complete trade history with timestamps
