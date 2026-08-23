# ORION Data Source Registry

This registry records availability and quality honestly. `DELAYED`, `UNOFFICIAL`,
`PROXY`, and `NOT AVAILABLE` are never represented as real-time.

| Provider | Assets | Latency | API/WebSocket | Auth | Quality tier | Fallback priority | Documentation |
|---|---|---|---|---|---|---|---|
| Coinbase public feed | BTC, ETH, XRP, SOL | exchange stream where connected | WebSocket | No | A for covered crypto | 1 | https://docs.cdp.coinbase.com/exchange/docs/websocket-overview |
| Yahoo Finance | GC/MGC proxy, indices, rates, DXY proxy | delayed/unofficial | documented public endpoint used by adapter | No | C / PROXY | 3 | https://finance.yahoo.com/ |
| CFTC reports | futures positioning | weekly delayed | public reports | No | B / DELAYED | 1 | https://www.cftc.gov/MarketReports/CommitmentsofTraders |
| RSS news providers | macro/markets/crypto | publisher-dependent | RSS/HTTP | No | B/C, delayed | 1 | provider feed URL stored per item |
| TradingView webhooks | user alerts | event delivery | Webhook | configured secret | A for received event | 1 | https://www.tradingview.com/support/solutions/43000529348-about-webhooks/ |

Order flow, DOM, dealer gamma, and exchange volume are `NOT AVAILABLE` unless a
provider supplies verifiable fields. ORION does not scrape TradingView or bypass
authentication/rate limits.
