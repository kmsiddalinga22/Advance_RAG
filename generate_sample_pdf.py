from fpdf import FPDF
from fpdf.enums import XPos, YPos

pdf = FPDF()
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()

pdf.set_font("Helvetica", "B", 16)
pdf.cell(0, 10, "VeloCart Platform - Technical & Product Documentation", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.ln(4)


def h1(title):
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)


def h2(title):
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)


def body(text):
    pdf.multi_cell(0, 5.5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)


def code_block(text):
    pdf.set_font("Courier", "", 8.5)
    pdf.set_fill_color(240, 240, 240)
    pdf.multi_cell(0, 4.5, text, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)


# ---------------------------------------------------------------------------
h1("1. Authentication & Session Management")

h2("1.1 Login Flow")
body(
    "Users authenticate with email and password via POST /api/v1/auth/login. "
    "On success, the server returns a JWT access token (15 minute expiry) and "
    "a refresh token (30 day expiry, httpOnly cookie). Failed attempts are "
    "rate-limited to 5 per 10 minutes per IP address."
)

h2("1.2 Multi-Factor Authentication")
body(
    "MFA is optional per-account, enabled in Account Settings. Supported "
    "methods: TOTP authenticator apps and SMS one-time codes. When MFA is "
    "enabled, login requires a second POST /api/v1/auth/mfa/verify call "
    "with the one-time code before tokens are issued."
)

h2("1.3 Session Timeout Behavior")
body(
    "Access tokens expire after 15 minutes of issuance regardless of activity. "
    "The frontend silently refreshes using the refresh token cookie every 12 "
    "minutes. If the refresh token itself has expired, the user is redirected "
    "to the login page with their previous location preserved as a return_to "
    "query parameter."
)

h2("1.4 Password Reset")
body(
    "Password reset is requested via POST /api/v1/auth/reset-request with an "
    "email address. A reset link valid for 1 hour is emailed if the account "
    "exists (the endpoint always returns 200 to avoid leaking account "
    "existence). The reset link token is single-use and invalidated after "
    "the first successful password change."
)

h2("1.5 Account Lockout Policy")
body(
    "After 5 consecutive failed login attempts, the account is locked for 15 "
    "minutes. Locked accounts can still request a password reset, which, if "
    "completed, immediately lifts the lockout regardless of the timer."
)

pdf.add_page()

# ---------------------------------------------------------------------------
h1("2. User Management API")

h2("2.1 Create User")
body("Creates a new user account. Requires admin scope.")
code_block(
    "POST /api/v1/users\n"
    "Content-Type: application/json\n"
    "Authorization: Bearer <admin_token>\n\n"
    "{\n"
    '  "email": "jane.doe@example.com",\n'
    '  "name": "Jane Doe",\n'
    '  "role": "member",\n'
    '  "send_invite": true\n'
    "}\n\n"
    "Response 201:\n"
    "{\n"
    '  "id": "usr_8f2a1c",\n'
    '  "email": "jane.doe@example.com",\n'
    '  "status": "invited",\n'
    '  "created_at": "2026-06-01T10:22:00Z"\n'
    "}"
)

h2("2.2 Update User Role")
body(
    "Roles form a hierarchy: viewer < member < admin < owner. Only owners can "
    "promote another user to owner. Admins can manage viewer/member/admin "
    "roles but cannot modify another admin's role without owner approval."
)

h2("2.3 Deactivate vs Delete")
body(
    "Deactivating a user (PATCH /api/v1/users/{id} with status=inactive) "
    "preserves all historical data and audit logs, and the seat is freed "
    "from billing. Deleting a user (DELETE /api/v1/users/{id}) is "
    "irreversible after a 30-day soft-delete grace period, during which an "
    "owner can restore the account via support."
)

pdf.add_page()

# ---------------------------------------------------------------------------
h1("3. Payments & Billing")

h2("3.1 Supported Payment Methods")
body(
    "Credit/debit cards (via Stripe), ACH bank transfer (US only, 3-5 "
    "business day settlement), and invoiced billing for Enterprise plans "
    "with net-30 terms."
)

h2("3.2 Subscription Tiers")
body("Pricing and included seats per tier:")
code_block(
    "Tier        | Monthly Price | Included Seats | Overage per Seat\n"
    "------------|---------------|-----------------|------------------\n"
    "Starter     | $29           | 3               | $12\n"
    "Growth      | $99           | 10              | $9\n"
    "Scale       | $349          | 30              | $7\n"
    "Enterprise  | Custom        | Custom          | Negotiated"
)

h2("3.3 Failed Payment Handling")
body(
    "On payment failure, the account enters a 7-day grace period with full "
    "feature access. Three retry attempts are made on days 1, 3, and 6. If "
    "all retries fail, the account is downgraded to a read-only state on "
    "day 8 until payment succeeds."
)

h2("3.4 Refund Policy")
body(
    "Refunds are prorated for annual plans cancelled within 30 days of "
    "purchase or renewal. Monthly plans are not eligible for partial-period "
    "refunds; cancellation takes effect at the end of the current billing "
    "cycle."
)

pdf.add_page()

# ---------------------------------------------------------------------------
h1("4. Search & Indexing")

h2("4.1 Index Update Latency")
body(
    "Newly created or updated records appear in search results within 2-5 "
    "seconds under normal load. During bulk imports (over 10,000 records), "
    "indexing latency can extend to several minutes; a queue depth metric "
    "is exposed at GET /api/v1/search/index-status."
)

h2("4.2 Query Syntax")
body(
    "Supports field-scoped queries (field:value), boolean operators (AND, "
    "OR, NOT), and fuzzy matching with a trailing tilde (term~1 allows edit "
    "distance 1). Wildcard prefix matching is supported (term*) but suffix "
    "wildcards are not."
)

h2("4.3 Localized Note")
body(
    "Nota para equipos internacionales: la busqueda distingue entre "
    "region-es, y los resultados pueden variar segun la configuracion de "
    "idioma de la cuenta. Se recomienda establecer explicitamente el "
    "parametro locale en cada solicitud de busqueda para resultados "
    "consistentes."
)

pdf.add_page()

# ---------------------------------------------------------------------------
h1("5. Notifications")

h2("5.1 Delivery Channels")
body(
    "Notifications can be delivered via in-app, email, and webhook. Webhook "
    "delivery includes automatic retry with exponential backoff (up to 5 "
    "attempts over 24 hours) and signs each payload with an HMAC-SHA256 "
    "signature in the X-Signature header."
)

h2("5.2 Notification Preferences")
body(
    "Users can mute individual notification categories independently. "
    "Security-related notifications (new device login, password changed) "
    "cannot be muted and are always delivered via email regardless of "
    "in-app preference settings."
)

h2("5.3 Digest Mode")
body(
    "When digest mode is enabled, non-urgent notifications are batched into "
    "a single email sent at the user's configured local time (default 9am), "
    "rather than sent individually as they occur."
)

pdf.add_page()

# ---------------------------------------------------------------------------
h1("6. Reporting & Analytics")

h2("6.1 Standard Reports")
body(
    "Pre-built reports include: Active Users (daily/weekly/monthly), "
    "Feature Adoption, Churn Risk Score, and Revenue by Tier. Reports refresh "
    "on a rolling 24-hour cycle; real-time data is available only via the "
    "Live Dashboard, which samples at 1-minute intervals."
)

h2("6.2 Custom Report Builder")
body(
    "Available on Growth tier and above. Supports up to 8 dimensions and 4 "
    "metrics per report, with export to CSV or scheduled email delivery. "
    "Custom reports referencing deleted fields are automatically disabled "
    "with an in-app notification to the report owner."
)

h2("6.3 Data Retention for Analytics")
body(
    "Raw event data is retained for 13 months. Aggregated daily rollups are "
    "retained indefinitely. Deleting a workspace purges raw event data "
    "within 30 days but aggregated historical rollups are retained in "
    "anonymized form for platform-wide benchmarking."
)

pdf.output("sample_docs/velocart_platform_docs.pdf")
print("PDF generated at sample_docs/velocart_platform_docs.pdf")
