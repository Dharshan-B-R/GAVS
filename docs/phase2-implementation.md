# Phase 2 implementation tracker

Phase 2 is being delivered incrementally on top of the existing Phase 1 application. The following backend intelligence slices have been added to the repository. They are not considered production-verified until the consolidated backend test suite, Flutter checks, migration review and realistic-data validation are completed.

## Implemented backend slices

| Capability | Implementation | API | Safety / data rule |
|---|---|---|---|
| Product Name Intelligence | Shop-scoped aliases, normalization and exact/fuzzy matching | `/shops/{shop_id}/product-aliases`, `/shops/{shop_id}/product-name-matches` | Fuzzy matches require human confirmation; aliases do not merge products |
| Expiry Intelligence | Batch expiry exposure and completed disposal-loss/credited-return summary | `GET /shops/{shop_id}/agents/expiry-risk` | Pending requests are not counted as realized losses; all at-risk batches contribute to totals |
| Stockout Risk | Stockout timing from recorded sale velocity and verified unexpired stock | `GET /shops/{shop_id}/agents/stockout-risk` | Unknown demand stays unknown; no orders are created |
| Seasonal Demand | Month-by-month observed sales patterns | `GET /shops/{shop_id}/agents/seasonal-demand` | Requires substantial history; missing months are not treated as zero; festival questions route to seasonal analysis |
| Festival / Event Demand | Compare a caller-specified event window with its preceding baseline | `GET /shops/{shop_id}/agents/event-demand` | Descriptive comparison only; no fabricated festival multiplier |
| Supplier Price Intelligence | Historical received-invoice price comparison by product and supplier | `GET /shops/{shop_id}/agents/supplier-prices` | Uses shop-owned products and received purchases only |

## Remaining Phase 2 work

1. Improve demand forecasting with validated seasonality and stockout-censored demand handling.
2. Purchase optimizer: combine demand, saleable stock, lead time, supplier prices and owner-set cash budget.
3. Supplier performance: delivery reliability, fill rate, price stability and issue history, only where source data exists.
4. Financial intelligence: shop-scoped khata aging, cash-flow visibility, working-capital and profitability analysis.
5. Multi-agent orchestration: structured intent routing, evidence summaries, confidence and safe fallbacks.
6. Integrations: invoice OCR, WhatsApp, UPI reconciliation, voice and local-language support.
7. Neighbourhood intelligence: opt-in, privacy-preserving aggregation with minimum cohort thresholds.
8. Flutter screens, alerts, recommendation feedback and daily summary.
9. Consolidated tests, authorization/isolation review, migration review and realistic-data validation.

## API safety

- Intelligence endpoints are read-only and require shop staff membership.
- All analytics must filter by the requested `shop_id`.
- AI recommendations do not spend money, create supplier commitments or execute purchases.
- Purchase execution remains a separate workflow requiring explicit owner approval.
- Insufficient history or missing observations must be reported rather than replaced with invented estimates.

## Validation status

New backend tests have been added alongside the intelligence services. They have not yet been run as part of the requested consolidated validation pass. Do not treat the presence of tests or commits as evidence that CI or production migration has passed.
