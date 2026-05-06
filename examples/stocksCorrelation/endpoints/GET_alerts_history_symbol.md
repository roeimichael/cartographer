# `GET /alerts/history/{symbol}`

- **operationId**: `get_alert_history`
- **tag**: routers
- **handler**: `src/api/routers/monitoring.py::get_alert_history`
- **call tree size**: 1 nodes, 1 edges
- **external calls**: 0 (top 15 below)

## Request
### Parameters
| Name | In | Required | Type | Description |
|------|-----|----------|------|-------------|
| `symbol` | path | True | string |  |

## Responses
- **200**: OK

## Internal call tree
_Handler has no internal calls — leaf-only endpoint._

## Internal modules touched
| File | Symbols touched |
|------|------------------|
| `src/api/routers/monitoring.py` | 1 |

## External dependencies (top 15)
_None or all internal._

## Cross-endpoint reuse
_No symbols shared with other endpoints._
