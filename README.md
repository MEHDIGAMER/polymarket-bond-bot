# Polymarket Bond Bot

Automated bond-strategy trader for Polymarket prediction markets.
**Paper-trade first. Real money only after edge is validated.**

## What it does

Buys near-resolved YES markets at $0.93-0.97 and holds to settlement, harvesting the 5.2% per cycle that whales run on the platform.

Based on the [Chaincatcher 95M-transaction analysis](https://www.chaincatcher.com/en/article/2233047): 90% of orders >$10K on Polymarket happen at price >$0.95. The bond strategy is what whales actually do; everything else is noise.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ scanner.py   — pulls markets every 60s, filters       │
│                bond candidates (price 0.93-0.97,       │
│                <120h to resolution, >$50K vol)         │
│                                                        │
│ trader.py    — opens positions (paper or live)         │
│                + Kelly-sized, half-fraction, 5% cap    │
│                                                        │
│ resolver.py  — checks resolution outcomes, updates     │
│                P&L, closes positions                   │
│                                                        │
│ filter_nlp.py — NLP check on resolution rules to       │
│                  skip ambiguous markets                │
│                                                        │
│ alerts.py    — Telegram bot for fills/P&L/errors       │
│                                                        │
│ report.py    — daily summary: win rate, drawdown,      │
│                edge metrics                            │
│                                                        │
│ db: SQLite (paper) → Postgres/Supabase (live)          │
└──────────────────────────────────────────────────────┘
```

## Risk controls (hardcoded, not config)

- Price band: 0.93 ≤ p ≤ 0.97
- Resolution window: 24h ≤ t ≤ 120h
- Volume floor: $50,000
- Order book depth: $5,000 within 1¢
- Max position: 5% of bankroll OR $2,500 (whichever lower)
- Max concurrent: 15 positions
- Max one category: 30% of bankroll
- Kill switch: -10% drawdown in 24h pauses trading
- Stop-loss: position price drops to $0.85 → exit

## Phases

| Phase | Capital | Mode | Goal | Duration |
|-------|---------|------|------|----------|
| 1 | $0 | PAPER | Validate edge: win rate >94%, avg return >4.5%, 50+ resolutions | 2-4 weeks |
| 2 | $5K | LIVE-SMALL | First real fills, 5-6 concurrent, manual review | 30 days |
| 3 | $15K | LIVE-AUTO | Add Telegram alerts only on errors, full automation | 60 days |
| 4 | $30K | LIVE-FULL | Add copy-trading + tail-sweep modules | ongoing |

**No phase advances without hitting its validation criteria.**

## Deploy

See `deploy/hetzner-setup.sh`. Bot runs as systemd daemon on a 4GB Hetzner VPS in Germany ($5/mo).

## License

MIT.
