# KiranaAI Phase 1 implementation

## Roles and access

- **Owner**: manages shop inventory, employees, connected suppliers, purchase budget, purchase proposals, approvals and internal purchase-order execution.
- **Employee**: uses shop inventory, stock receiving/verification, sales and read-only AI analysis. Cannot manage the budget or approve/execute purchase proposals.
- **Supplier**: sees purchase orders addressed to its supplier account and can confirm them.
- **Admin**: has a separate landing point; platform administration is not part of the shop workflow in this phase.

The authenticated role comes from the backend user record. The client does not let users select their own role. Shop data requests include a shop ID and are checked against active shop membership by the backend.

## Inventory workflow

1. Create a product with zero recorded stock.
2. Add stock with a batch number and expiry date.
3. Verify the physical batch quantity. Unverified batches are not saleable.
4. Record sales. The sales endpoint checks verified, unexpired batch stock and deducts quantities using FEFO batch selection.
5. Record stock corrections through the audited adjustment endpoint. Positive adjustments require a new batch; negative adjustments reduce existing batches.

Product quantity is not directly editable. Product records are archived rather than hard-deleted so historical sale and stock records remain intact.

## AI and forecasting

- The inventory agent reads shop-scoped inventory and stock-movement data.
- Forecast and reorder services calculate demand and suggested replenishment quantities.
- The orchestrator can return inventory, sales, forecast, reorder, supplier and pending-approval information.
- AI analysis is read-only. It cannot change inventory or create/approve purchase orders.

## Purchase workflow

1. The Owner sets the available INR cash budget.
2. The Owner connects an active supplier.
3. KiranaAI recommendations can be converted into a pending purchase proposal.
4. The Owner approves or rejects the proposal.
5. Only an approved proposal can be executed into an internal Purchase Order. Execution is idempotent.
6. The supplier sees the order in the supplier workspace and can confirm it.
7. Shop staff record goods receipt with a batch number and expiry date for every order line.
8. Received batches remain unverified until physically verified. Receiving goods is the step that increases stock.

The current supplier workspace supports in-app order visibility and confirmation. It does not send external email/WhatsApp orders or connect to supplier ERP systems.

## Employee workflow

- An Owner creates a time-limited, one-use invitation token for an email address.
- The invited employee accepts the token and creates a password.
- The employee is assigned an Employee membership for that shop.
- Owners can suspend or reactivate the membership.
- Only a hash of the invitation token is stored.

## Tenant-safety notes

Legacy endpoints that were not safely shop-scoped are disabled with HTTP 410. Use the shop-specific APIs for shop operations. Existing scoped product, sale, purchase receipt, batch verification and inventory summary endpoints remain available.

## Local verification

Backend, from backend/:

```powershell
python -m pytest tests -v
```

Flutter, from mobile_app/:

```powershell
flutter pub get
flutter analyze
flutter run -d chrome
```

The GitHub Actions workflow .github/workflows/phase1-ci.yml runs backend tests against an isolated PostgreSQL test database and runs Flutter analysis.
