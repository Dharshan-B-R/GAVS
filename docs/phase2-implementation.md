# Phase 2 implementation tracker

Phase 2 is being delivered incrementally on top of Phase 1. Implementation status below is based on committed code, not runtime verification. The consolidated test suite, Flutter checks, migration review and realistic-data validation remain deliberately on hold per the project instruction.

## Intelligence foundation already implemented

| Capability | Backend implementation | API | Guardrail |
|---|---|---|---|
| Product Name Intelligence | Shop-scoped aliases, normalization and exact/fuzzy matching | `/shops/{shop_id}/product-aliases`, `/shops/{shop_id}/product-name-matches` | Fuzzy matches require human confirmation |
| Expiry Intelligence | Batch expiry exposure, recorded disposal loss and supplier-credit reconciliation | `GET /shops/{shop_id}/agents/expiry-risk` | Pending actions are not realized losses |
| Dead Stock | Mature active products with positive inventory and no recorded sale | `GET /shops/{shop_id}/agents/dead-stock` | Missing history is not treated as proof of no demand |
| Stockout Risk | Recorded sale velocity vs verified, unexpired saleable stock | `GET /shops/{shop_id}/agents/stockout-risk` | Unknown demand remains unknown |
| Seasonal Demand | Observed monthly sales patterns | `GET /shops/{shop_id}/agents/seasonal-demand` | Unobserved months remain null |
| Festival / Event Demand | Completed caller-defined event window vs preceding baseline | `GET /shops/{shop_id}/agents/event-demand` | No assumed festival multiplier |
| Supplier Price Intelligence | Weighted price comparisons from received invoices | `GET /shops/{shop_id}/agents/supplier-prices` | Does not normalize pack size/tax/freight |
| Demand Forecast | Sales velocity with selling-day coverage, observed weekday profile and confidence metadata | `GET /shops/{shop_id}/agents/forecast` | No imputed demand or automatic seasonal uplift |
| Cash-aware Reorder Ranking | Saleable stock, lead time, safety stock, forecast confidence and owner-set budget prioritization | `GET /shops/{shop_id}/agents/reorder-recommendations` | Advisory only; no proposal or PO is created |
| Supplier Performance | Recorded received-order volume/value and evidence availability | `GET /shops/{shop_id}/agents/supplier-performance` | Reliability/fill rate withheld until promised and short-receipt data exists |
| Financial Position | Read-only supplier payables; khata returned unavailable unless customer ownership is shop-scoped | `GET /shops/{shop_id}/agents/financial-position` | Does not aggregate cross-shop customer balances |
| Agent Orchestration | Expanded specialist routing, result aggregation and safe partial-result reporting | `POST /shops/{shop_id}/agents/orchestrate` | Staff restrictions retained; read-only |

## Implemented in this completion branch

1. Forecast outputs now report selling-day coverage and observed weekday data. Sparse history is low confidence; no-sale periods are not treated as proven zero demand.
2. Reorder recommendations now prioritize stockout urgency and forecast confidence, then fit ranked candidate recommendations within the configured owner cash budget. Deferred items remain visible.
3. Supplier performance endpoint reports only recorded received purchase evidence. On-time rate, fill rate and issue rate remain unavailable because the current schema lacks promised dates, ordered-vs-received quantities and supplier-issue records.
4. Financial position endpoint reports supplier payables from received purchases less recorded payments. Customer khata is intentionally withheld until customer ownership can be safely attributed to a shop; customer rows have no shop_id.
5. Orchestrator understands expiry, financial and event intents and returns specialist results with explicit partial/insufficient evidence states.
6. New API endpoints are staff-authorized and filtered using the requested shop id.

## Remaining before Phase 2 can be called fully complete

- Persist customer-to-shop ownership or shop-customer membership, then enable shop-scoped khata ageing.
- Add promised delivery date, ordered quantity, received quantity and dispute/issue models before calculating true supplier performance.
- Correctly model lost demand during stockouts with availability snapshots or POS out-of-stock events.
- Add explicit festival calendar and locality configuration; event comparisons must remain grounded in actual recorded history.
- Complete Flutter screens, API wiring, notifications, recommendation feedback and daily summaries.
- Review migration compatibility and tenant isolation; add migrations only after confirming actual schema requirements.
- Run consolidated backend tests, Flutter analysis/build, migration review and realistic-data validation only after explicit approval to test.

## API safety

- Intelligence endpoints are read-only and require shop staff membership.
- All product/sales/purchase metrics are filtered by the requested shop.
- Purchase recommendations do not create proposals, spend money, contact suppliers or place orders.
- Purchase execution remains a separate owner-approved workflow.
- Insufficient history, missing data and unavailable metrics are reported explicitly rather than fabricated.

## Validation status

**Testing is intentionally not run.** No test suite, Flutter analysis, migration, CI workflow or production data operation has been executed as part of this completion work. A code commit is not proof of test or production readiness.
