# Endpoint trace index
- Total endpoints: **21**
- Linked to handler: **21**

## Top 15 endpoints by call-tree size
| Method | Path | Tag | Nodes | Files touched | Card |
|--------|------|-----|-------|---------------|------|
| GET | `/portfolio` | routers | 4 | 2 | [detail](endpoints/GET_portfolio.md) |
| GET | `/summary/stats` | routers | 4 | 2 | [detail](endpoints/GET_summary_stats.md) |
| GET | `/pairs/{symbol1}/{symbol2}` | routers | 2 | 1 | [detail](endpoints/GET_pairs_symbol1_symbol2.md) |
| GET | `/` | routers | 1 | 1 | [detail](endpoints/GET.md) |
| GET | `/api/health` | api | 1 | 1 | [detail](endpoints/GET_api_health.md) |
| GET | `/matrix` | routers | 1 | 1 | [detail](endpoints/GET_matrix.md) |
| GET | `/alerts/latest` | routers | 1 | 1 | [detail](endpoints/GET_alerts_latest.md) |
| GET | `/alerts/date/{date}` | routers | 1 | 1 | [detail](endpoints/GET_alerts_date_date.md) |
| GET | `/alerts/history/{symbol}` | routers | 1 | 1 | [detail](endpoints/GET_alerts_history_symbol.md) |
| POST | `/daily` | routers | 1 | 1 | [detail](endpoints/POST_daily.md) |
| POST | `/backtest` | routers | 1 | 1 | [detail](endpoints/POST_backtest.md) |
| POST | `/gridsearch` | routers | 1 | 1 | [detail](endpoints/POST_gridsearch.md) |
| POST | `/preprocess` | routers | 1 | 1 | [detail](endpoints/POST_preprocess.md) |
| GET | `/status/{task_id}` | routers | 1 | 1 | [detail](endpoints/GET_status_task_id.md) |
| GET | `/tasks` | routers | 1 | 1 | [detail](endpoints/GET_tasks.md) |

## Functions called from 2+ endpoints (top 20)
| Symbol | File:Line | Used by N endpoints |
|--------|-----------|----------------------|
| `get_correlation_matrix` | `src/api/routers/correlations.py:18` | 2 |
| `_calculate_days_held` | `src/api/services/positions_service.py:131` | 2 |
| `_empty_response` | `src/api/services/positions_service.py:142` | 2 |
| `get_all_positions` | `src/api/services/positions_service.py:23` | 2 |