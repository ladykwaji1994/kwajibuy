# KwajiBuy

KwajiBuy is a Nigerian marketplace MVP built with Python and Flet. Its storefront takes cues from the category-led, search-first shopping flow of Jumia, while focusing its own identity on trusted local sellers and everyday finds.

## Run locally

Requires Python 3.9 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

The app opens in a browser at `http://localhost:8550`. The SQLite database is created at `data/kwajibu.sqlite3`. Set `KWAJIBUY_DB_PATH` to use a different location.

To show the login page's one-click demo role cards on a local demo, start with `KWAJIBUY_ENABLE_DEMO_ACCOUNTS=1 python main.py`. The cards are for `demo.shopper@kwajibuy.local`, `demo.seller@kwajibuy.local`, and `demo.admin@kwajibuy.local`; no password is displayed or stored in browser storage. Keep this flag off outside local demos.

Create the first admin from server environment variables. Use a unique password of at least 12 characters; admin registration is not available through public signup.

## MVP workflows

- Browse a seeded catalog in Naira; filter by category or search product, category, and seller names.
- Add products to the session bag; open `/cart` to review quantities and subtotal, adjust/remove items, and continue to checkout.
- Register or sign in at `/account`; shopper profiles and orders are scoped to the authenticated account.
- Apply as a seller; pending accounts reach `/seller` and wait for admin approval.
- Place a pay-on-delivery order. The order and its line items are written to SQLite with fulfilment and payment status.
- Configure Paystack to accept hosted card/bank-transfer checkout; the secret stays server-side, and verified payment updates the order.
- Sign in as admin to `/admin` to review order/payment metrics, update fulfilment status, and approve/reject seller applications.
- Open the returns, privacy, and terms notices in the footer.
- Resize for mobile and desktop; use the appearance control to switch the Flet theme.

## Admin and Paystack setup

Set the bootstrap admin credentials before starting the server. The admin account is created once if its email is not already registered. Online payment stays unavailable until a Paystack secret is configured.

```bash
export KWAJIBUY_ADMIN_EMAIL="admin@example.com"
export KWAJIBUY_ADMIN_PASSWORD="replace-with-a-unique-12-character-password"
export KWAJIBUY_PAYSTACK_SECRET_KEY="sk_test_replace-with-your-test-secret"
export KWAJIBUY_PAYSTACK_CALLBACK_URL="https://your-public-host/api/payments/paystack/callback"
python main.py
```

Shopper/seller API: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, and `POST /api/auth/logout`. Login returns a random bearer token; only its hash is stored in SQLite, with a 30-day expiry. Public signup permits `shopper` or `seller`; seller applications remain pending. Admin accounts are bootstrapped from environment, never self-selected at signup.

Use Paystack test credentials until payment testing is complete. Configure the Paystack webhook URL as `https://your-public-host/api/payments/paystack/webhook`. The webhook validates `x-paystack-signature` with HMAC-SHA512, checks successful NGN amount/currency against the saved order, and records each reference once. The browser callback independently verifies the reference through Paystack before updating payment status.

Admin endpoints:

- `GET /api/admin/orders` with the `x-admin-token` header returns orders and line items.
- `PATCH /api/admin/orders/{order_id}?status=confirmed` with the same header changes fulfilment status. Supported values: `new`, `confirmed`, `dispatched`, `delivered`, `cancelled`.
- `GET /api/admin/sellers` and `PATCH /api/admin/sellers/{user_id}?status=approved` list and review seller applications.
- Use an authenticated admin login token in `x-admin-token`, or configure `KWAJIBUY_ADMIN_TOKEN` for service-to-service/admin automation.
- The routed dashboard is available at `/admin`; it requires a signed-in admin account before showing store data.

## Coursework architecture

- **Presentation:** responsive Flet storefront, search, filters, product cards, cart, checkout, and policy dialogs.
- **Logic:** in-memory catalog and per-session cart, category/search filtering, checkout validation, payment initialization, and order reference generation.
- **Data:** SQLite `users`, `user_sessions`, `seller_profiles`, `customer_profiles`, `orders`, `order_items`, and `payment_events` tables, created/migrated on startup. Passwords use PBKDF2-HMAC-SHA256; login tokens are random, hashed at rest, and revocable. Payment event processing is transactional and idempotent.
- **Trust and accessibility:** verified-seller labels, ratings, pay-on-delivery checkout, return information, labeled form fields, and tooltips on icon controls.

## Docker

```bash
docker build -t kwajibuy .
docker run --rm -p 8550:8550 -v kwajibuy-data:/app/data \
	-e KWAJIBUY_ADMIN_TOKEN="$KWAJIBUY_ADMIN_TOKEN" \
	-e KWAJIBUY_PAYSTACK_SECRET_KEY="$KWAJIBUY_PAYSTACK_SECRET_KEY" \
	-e KWAJIBUY_PAYSTACK_CALLBACK_URL="https://your-public-host/api/payments/paystack/callback" \
	kwajibuy
```

Open `http://localhost:8550`. The named volume preserves orders when the container is recreated.

## Demo scope and production work

This is an MVP, not a production commerce service. It uses sample products and remote product imagery. The seller portal covers registration and approval status, not product publishing, inventory, or payouts. The cart is session-only. Before production, add email verification, password reset, login throttling/MFA for admins, secure cookie/session protections, role audit logs, and account recovery. Paystack live mode requires merchant onboarding, HTTPS, verified production callbacks, reconciliation, refund handling, and operational monitoring. Demo order data includes contact and address details; protect and delete local demo data appropriately. The policy dialogs are coursework examples, not legal advice or a compliance certification. Before launch, replace them with reviewed policies aligned with Nigeria's NDPA 2023 and applicable GDPR requirements; add data retention/deletion workflows, HTTPS, payment security, monitoring, backups, and security testing against the OWASP Top Ten.

## Manual MVP test

1. Search for `Sound House`; confirm the two matching electronics products appear.
2. Register/sign in as a shopper, filter to `Fashion`, add an item, and open `/cart`.
3. Remove an item, then add a product again and proceed to checkout.
4. Submit with a required field blank; confirm validation keeps checkout open.
5. Complete all fields and place a pay-on-delivery order; confirm an order reference appears and the bag count returns to zero.
6. Save a shopper profile and confirm its delivery details prefill checkout.
7. Sign out and back in; confirm the shopper's order history is scoped to that account.
8. Apply as a seller, sign in, and confirm the seller remains pending until admin approval.
9. Set the bootstrap admin env vars, sign in as admin, open `/admin`, approve the seller, and update an order status.
10. Confirm rows exist in `data/kwajibu.sqlite3` in `users`, `seller_profiles`, `orders`, and `order_items`.
11. With Paystack test keys configured, place a test online order and verify the signed webhook updates its payment status once.