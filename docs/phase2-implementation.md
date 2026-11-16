# Phase 2 implementation tracker

Phase 2 intelligence is implemented incrementally on the dedicated `phase2-intelligence-completion` branch. This tracker distinguishes code that has been added from evidence that still requires real shop activity. Backend tests, Flutter checks, migration execution and realistic-data validation remain deliberately on hold until the project is ready for one consolidated test session.

## Intelligence capabilities

| Capability | Implementation | API / app entry | Evidence and guardrail |
|---|---|---|---|
| Product Name Intelligence | Shop-scoped aliases, normalization and exact/fuzzy matching | Product alias APIs | Fuzzy matches require human confirmation |
| Expiry Intelligence | Batch expiry exposure, recorded disposal loss and supplier-credit reconciliation | `GET /shops/{shop_id}/agents/expiry-risk` | Pending actions are not realized losses |
| Dead Stock | Mature active products with positive inventory and no recorded sale | `GET /shops/{shop_id}/agents/dead-stock` | Missing history is not proof of no demand |
| Stockout Risk | Recorded sale velocity vs verified, unexpired saleable stock | `GET /shops/{shop_id}/agents/stockout-risk` | Stockout-censored demand remains unknown without availability observations |
| Availability History | Daily saleable batch snapshots, with one shop/product/date observation | `POST /shops/{shop_id}/availability-snapshots/capture`; `backend/scripts/capture_daily_availability.py` | Flutter has a manual action and a cron-ready all-shop command; deployment must configure the schedule |
| Demand Forecast | Observed sales velocity, selling-day coverage, weekday profile and availability-adjusted velocity when snapshots cover at least half the requested window | `GET /shops/{shop_id}/agents/forecast` | Sparse or incomplete evidence is low confidence; no automatic seasonal uplift |
| Seasonal Demand | Observed monthly sales patterns | `GET /shops/{shop_id}/agents/seasonal-demand` | Unobserved months remain null |
| Festival / Event Demand | Shop-owned event calendar and event-window vs preceding baseline comparison | `/shops/{shop_id}/festival-calendar`, `GET /shops/{shop_id}/agents/event-demand/{event_id}` | Owner enters local events; only completed windows are compared |
| Cash-aware Reorder Ranking | Saleable stock, lead time, safety stock, forecast confidence and owner-set budget prioritization | `GET /shops/{shop_id}/agents/reorder-recommendations` | Advisory only; no proposal or PO is created |
| Supplier Price Intelligence | Weighted price comparisons from received invoices | `GET /shops/{shop_id}/agents/supplier-prices` | Does not normalize pack size/tax/freight |
| Supplier Performance | Ordered vs received quantity, promised vs actual delivery date and shop-recorded supplier issues | `GET /shops/{shop_id}/agents/supplier-performance` | Legacy records without dates are excluded from on-time denominator |
| Supplier Issues | Shop-scoped issue reporting, severity and resolution tracking | `/shops/{shop_id}/supplier-issues` | Issue rate is only calculated from issues linked to eligible purchase orders |
| Financial Position | Shop-scoped khata receivables and supplier payables | `GET /shops/{shop_id}/agents/financial-position` | Legacy customers remain excluded until an owner explicitly assigns them |
| Agent Orchestration | Specialist routing, saved event comparisons, evidence and partial-result reporting | `POST /shops/{shop_id}/agents/orchestrate` | Read-only; staff/owner restrictions retained |
| Flutter Intelligence | Dedicated Intelligence tab for snapshots, local calendar, khata ledger, supplier issues and specialist results | Mobile app | Owner-only configuration actions remain gated in UI and API |

## Data foundation added in this branch

- `customers.shop_id` is nullable. New customers are created under a shop; old records are not automatically assigned. An owner can explicitly assign a known legacy customer ID, carrying its existing ledger history to that shop.
- `purchases.expected_delivery_date` and `purchases.received_at` support on-time delivery measurement. Owners record the promised date before receipt; the receipt workflow records actual receipt time.
- `purchases.invoice_amount` and `supplier_invoice_number` separate the real supplier invoice from the internal PO estimate. Internal PO estimates are excluded from payable balances until invoice details are entered.
- `purchase_items.ordered_quantity` and `received_quantity` preserve ordered-vs-received quantities. Historical received rows are backfilled as fully received because earlier records had only one quantity field.
- `shops.city`, `state`, `country` and `timezone` support shop-local event context. City/state can be configured from the Flutter Intelligence tab.
- `festival_events` stores shop-specific festivals, local events, promotions and market days.
- `inventory_availability_snapshots` stores saleable quantity and availability per product per date.
- `supplier_issues` stores shop-scoped supplier issues, optional purchase linkage, severity and resolution state.

## Remaining operational requirements

1. **Daily availability capture:** The app currently exposes a manual capture action. A cron-ready all-shop command is included at `backend/scripts/capture_daily_availability.py`. Configure it in the deployment environment so snapshot coverage is consistent without staff remembering to tap the button.
2. **Local festival seed data:** Each shop owner should enter/confirm the relevant local calendar. No festival uplift is guessed from city alone.
3. **Supplier issue linkage:** Staff should attach a purchase ID when reporting a supplier issue; unlinked issues are counted but do not inflate the per-order issue rate.
4. **Khata legacy mapping:** Owners must map old customer IDs to the correct shop. Unassigned legacy customers are intentionally excluded from shop financial totals.
5. **Accounting precision:** Khata ageing is based on oldest transaction, not contractual due dates. Cash balance, UPI/bank settlement and supplier invoice due dates need separate ledger data before cash-flow forecasting can be claimed.
6. **Supplier evidence coverage:** Old purchases without promised dates or actual receipt timestamps do not contribute to on-time delivery rate. Future orders must have expected dates entered and receipt workflow completed.
7. **Festival model quality:** Event comparisons require completed event windows and sufficient pre-event baseline history. Promotions, weather, stock availability and price effects are not causally separated yet.
8. **Consolidated verification:** Run backend tests, Flutter analysis/build, migration review on a database copy, API permission checks and realistic-data validation only after explicit approval to test.

## API and safety rules

- New intelligence data APIs are shop-scoped and use staff or owner dependencies as appropriate.
- Legacy customer assignment is owner-only and refuses to move a customer already assigned to another shop.
- Supplier issue creation requires an active supplier connection to the shop; a linked purchase must belong to that same shop and supplier.
- Purchase recommendations never create proposals, spend money, contact suppliers or place orders.
- Purchase order creation remains a separate owner-approved workflow; goods receipt is a separate recorded operation.
- Missing history, unreported issue rates and unavailable accounting fields are represented as unknown rather than fabricated.

## Validation status

**Testing is intentionally not run.** No test suite, Flutter analysis/build, migration execution, CI workflow or production data operation has been executed for this branch. The new Alembic revisions must be reviewed and applied to a disposable/staging database before production rollout. A code commit is not proof of runtime or production readiness.
