# OpenAPI summary

- Title: Synthetic OpenAPI from project-cartographer
- Version: synth
- Endpoints: 21

**Note:** synthesized from static endpoint detection — schemas are minimal. Run your server and pass `--live-url http://localhost:PORT/openapi.json` for full schemas.

## Endpoints
| Method | Path | Operation | Tag | Handler |
|--------|------|-----------|-----|---------|
| GET | `/` | `get_trade_history` | routers | `src/api/routers/trades.py::get_trade_history` |
| GET | `/alerts/date/{date}` | `get_alerts_by_date` | routers | `src/api/routers/monitoring.py::get_alerts_by_date` |
| GET | `/alerts/history/{symbol}` | `get_alert_history` | routers | `src/api/routers/monitoring.py::get_alert_history` |
| GET | `/alerts/latest` | `get_latest_alerts` | routers | `src/api/routers/monitoring.py::get_latest_alerts` |
| GET | `/api/health` | `health_check` | api | `src/api/main.py::health_check` |
| POST | `/backtest` | `run_backtest` | routers | `src/api/routers/operations.py::run_backtest` |
| POST | `/daily` | `run_daily_workflow` | routers | `src/api/routers/operations.py::run_daily_workflow` |
| GET | `/date/{date}` | `get_signals_by_date` | routers | `src/api/routers/signals.py::get_signals_by_date` |
| POST | `/gridsearch` | `run_gridsearch` | routers | `src/api/routers/operations.py::run_gridsearch` |
| GET | `/history/{symbol}` | `get_signal_history` | routers | `src/api/routers/signals.py::get_signal_history` |
| GET | `/latest` | `get_latest_signals` | routers | `src/api/routers/signals.py::get_latest_signals` |
| GET | `/matrix` | `get_correlation_matrix` | routers | `src/api/routers/correlations.py::get_correlation_matrix` |
| GET | `/pairs/{symbol1}/{symbol2}` | `get_pair_correlation` | routers | `src/api/routers/correlations.py::get_pair_correlation` |
| GET | `/performance/by-symbol` | `get_performance_by_symbol` | routers | `src/api/routers/trades.py::get_performance_by_symbol` |
| GET | `/portfolio` | `get_portfolio_correlation` | routers | `src/api/routers/correlations.py::get_portfolio_correlation` |
| POST | `/preprocess` | `run_preprocess` | routers | `src/api/routers/operations.py::run_preprocess` |
| GET | `/recent` | `get_recent_trades` | routers | `src/api/routers/trades.py::get_recent_trades` |
| GET | `/status/{task_id}` | `get_task_status` | routers | `src/api/routers/operations.py::get_task_status` |
| GET | `/summary/stats` | `get_positions_summary` | routers | `src/api/routers/positions.py::get_positions_summary` |
| GET | `/tasks` | `list_tasks` | routers | `src/api/routers/operations.py::list_tasks` |
| GET | `/{symbol}` | `get_position_by_symbol` | routers | `src/api/routers/positions.py::get_position_by_symbol` |