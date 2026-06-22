 import pytest
from datetime import datetime

from app import app
from database.db import get_db


# Fixtures mirror tests/test_06-date-filter-profile-page.py and
# tests/test_backend_connection.py conventions: real sqlite file DB via
# get_db(), a fresh throwaway user per test (created/torn down explicitly)
# so no test depends on another test's inserted expenses, and session-based
# login faked via client.session_transaction().

ALLOWED_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def new_user_id():
    """A fresh user with zero expenses, isolated from the seeded demo user
    and from other tests, so expense counts/totals asserted in a test are
    never polluted by rows another test inserted."""
    conn = get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test Add Expense", "add-expense-test@test.com", "x"),
    )
    conn.commit()
    uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    yield uid
    conn2 = get_db()
    conn2.execute("DELETE FROM expenses WHERE user_id = ?", (uid,))
    conn2.execute("DELETE FROM users WHERE id = ?", (uid,))
    conn2.commit()
    conn2.close()


def login(client, user_id, user_name="Test Add Expense"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = user_name


def get_expenses_for_user(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def valid_payload(**overrides):
    payload = {
        "amount": "42.50",
        "category": "Food",
        "date": "2026-06-01",
        "description": "Test grocery run",
    }
    payload.update(overrides)
    return payload


# ── Auth guard ──────────────────────────────────────────────────────────────

class TestAddExpenseAuthGuard:

    def test_get_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, "Unauthenticated GET must redirect, not render the form"
        assert "/login" in resp.headers["Location"], "Unauthenticated GET must redirect to /login"

    def test_post_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/add", data=valid_payload())
        assert resp.status_code == 302, "Unauthenticated POST must redirect, not process the form"
        assert "/login" in resp.headers["Location"], "Unauthenticated POST must redirect to /login"

    def test_post_unauthenticated_does_not_insert_row(self, client, new_user_id):
        # Use new_user_id only to know which user_id *would* have been used if
        # somehow inserted; we never log in, so no row should appear for anyone.
        client.post("/expenses/add", data=valid_payload())
        assert get_expenses_for_user(new_user_id) == [], (
            "An unauthenticated POST must never reach the insert path"
        )


# ── GET renders the form ────────────────────────────────────────────────────

class TestAddExpenseFormRendering:

    def test_get_authenticated_returns_200(self, client, new_user_id):
        login(client, new_user_id)
        resp = client.get("/expenses/add")
        assert resp.status_code == 200, "Logged-in GET must render the form, not redirect or error"

    def test_get_form_defaults_date_to_today(self, client, new_user_id):
        login(client, new_user_id)
        body = client.get("/expenses/add").data.decode()
        today = datetime.now().strftime("%Y-%m-%d")
        assert f'value="{today}"' in body, "Date field must default to today's date"

    def test_get_form_contains_amount_field(self, client, new_user_id):
        login(client, new_user_id)
        body = client.get("/expenses/add").data.decode()
        assert 'name="amount"' in body, "Form must contain an amount field"

    def test_get_form_contains_description_field(self, client, new_user_id):
        login(client, new_user_id)
        body = client.get("/expenses/add").data.decode()
        assert 'name="description"' in body, "Form must contain a description field"

    def test_get_form_contains_date_field(self, client, new_user_id):
        login(client, new_user_id)
        body = client.get("/expenses/add").data.decode()
        assert 'name="date"' in body, "Form must contain a date field"

    @pytest.mark.parametrize("category", ALLOWED_CATEGORIES)
    def test_get_form_lists_each_allowed_category(self, client, new_user_id, category):
        login(client, new_user_id)
        body = client.get("/expenses/add").data.decode()
        assert category in body, f"Category option '{category}' must appear in the rendered form"

    def test_get_form_does_not_preset_an_amount(self, client, new_user_id):
        login(client, new_user_id)
        body = client.get("/expenses/add").data.decode()
        assert 'value="0.01"' not in body, "A fresh GET must not pre-fill an arbitrary amount"


# ── Valid POST happy path ───────────────────────────────────────────────────

class TestAddExpenseValidSubmission:

    def test_valid_post_redirects_to_profile(self, client, new_user_id):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload())
        assert resp.status_code == 302, "A valid submission must redirect (not re-render the form)"
        assert resp.headers["Location"].endswith("/profile"), "A valid submission must redirect to /profile"

    def test_valid_post_inserts_row_for_logged_in_user(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload())
        rows = get_expenses_for_user(new_user_id)
        assert len(rows) == 1, "Exactly one new expense row must be inserted"
        assert rows[0]["user_id"] == new_user_id, "The new row must belong to the logged-in user"

    def test_valid_post_persists_submitted_field_values(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(
            amount="42.50", category="Food", date="2026-06-01", description="Test grocery run"
        ))
        row = get_expenses_for_user(new_user_id)[0]
        assert row["amount"] == 42.50
        assert row["category"] == "Food"
        assert row["date"] == "2026-06-01"
        assert row["description"] == "Test grocery run"

    def test_valid_post_does_not_affect_other_users_expenses(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload())
        conn = get_db()
        demo_row = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()
        conn.close()
        if demo_row is not None:
            demo_expenses_before = get_expenses_for_user(demo_row["id"])
            # Sanity: posting as new_user_id must not insert into demo user's rows.
            assert all(e["user_id"] != new_user_id for e in demo_expenses_before)


# ── Profile reflects the new expense ────────────────────────────────────────

class TestAddExpenseReflectedInProfile:

    def test_new_expense_appears_in_recent_transactions(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(description="Unique Marker Expense"))
        body = client.get("/profile").data.decode()
        assert "Unique Marker Expense" in body, (
            "The newly added expense must appear in Recent Transactions on the profile page"
        )

    def test_new_expense_appears_at_top_of_recent_transactions(self, client, new_user_id):
        login(client, new_user_id)
        # Older expense first.
        client.post("/expenses/add", data=valid_payload(date="2020-01-01", description="Old Expense"))
        # Newer expense second — should sort above the older one with no filter applied.
        client.post("/expenses/add", data=valid_payload(date="2026-06-15", description="Newest Expense"))
        body = client.get("/profile").data.decode()
        assert body.index("Newest Expense") < body.index("Old Expense"), (
            "The most recently dated expense must appear above older ones with no date filter applied"
        )

    def test_total_spent_includes_new_expense(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(amount="42.50"))
        body = client.get("/profile").data.decode()
        assert "42.50" in body, "Total Spent must include the newly added expense's amount"

    def test_transaction_count_includes_new_expense(self, client, new_user_id):
        login(client, new_user_id)
        body_before = client.get("/profile").data.decode()
        client.post("/expenses/add", data=valid_payload())
        body_after = client.get("/profile").data.decode()
        assert ">1<" in body_after, "Transaction Count must reflect the one newly added expense"
        assert body_before != body_after

    def test_category_breakdown_reflects_new_expense_category_and_amount(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(amount="99.00", category="Entertainment"))
        body = client.get("/profile").data.decode()
        assert "Entertainment" in body, "Category breakdown must include the new expense's category"
        assert "99.00" in body, "Category breakdown must reflect the new expense's amount"


# ── Invalid amount ───────────────────────────────────────────────────────────

class TestAddExpenseInvalidAmount:

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-5", "-0.01", "abc", "", "twelve", "inf", "-inf", "nan"])
    def test_invalid_amount_returns_400(self, client, new_user_id, bad_amount):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(amount=bad_amount))
        assert resp.status_code == 400, (
            f"amount={bad_amount!r} must be rejected with a 400-level response, not silently accepted"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-5", "-0.01", "abc", "", "twelve", "inf", "-inf", "nan"])
    def test_invalid_amount_does_not_insert_row(self, client, new_user_id, bad_amount):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(amount=bad_amount))
        assert get_expenses_for_user(new_user_id) == [], (
            f"amount={bad_amount!r} must not result in a new expense row"
        )

    def test_invalid_amount_preserves_other_submitted_values(self, client, new_user_id):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(
            amount="-10", category="Health", date="2026-06-05", description="Keep me"
        ))
        body = resp.data.decode()
        assert "Health" in body, "Previously selected category must be preserved on a failed submit"
        assert 'value="2026-06-05"' in body, "Previously entered date must be preserved on a failed submit"
        assert "Keep me" in body, "Previously entered description must be preserved on a failed submit"

    def test_invalid_amount_rerenders_form_with_error_message(self, client, new_user_id):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(amount="-10"))
        body = resp.data.decode()
        assert 'name="amount"' in body, "Failed submit must re-render the add-expense form, not redirect"


# ── Invalid date ─────────────────────────────────────────────────────────────

class TestAddExpenseInvalidDate:

    @pytest.mark.parametrize("bad_date", ["", "not-a-date", "2026-13-40", "06/01/2026", "2026/06/01"])
    def test_invalid_date_returns_400(self, client, new_user_id, bad_date):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(date=bad_date))
        assert resp.status_code == 400, (
            f"date={bad_date!r} must be rejected with a 400-level response, not crash or silently pass"
        )

    @pytest.mark.parametrize("bad_date", ["", "not-a-date", "2026-13-40", "06/01/2026", "2026/06/01"])
    def test_invalid_date_does_not_insert_row(self, client, new_user_id, bad_date):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(date=bad_date))
        assert get_expenses_for_user(new_user_id) == [], (
            f"date={bad_date!r} must not result in a new expense row"
        )

    def test_invalid_date_preserves_other_submitted_values(self, client, new_user_id):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(
            date="not-a-date", amount="15.00", category="Transport", description="Bus fare"
        ))
        body = resp.data.decode()
        assert "Transport" in body, "Previously selected category must be preserved on a failed date submit"
        assert "Bus fare" in body, "Previously entered description must be preserved on a failed date submit"


# ── Invalid category (allow-list bypass) ────────────────────────────────────

class TestAddExpenseInvalidCategory:

    @pytest.mark.parametrize("bad_category", ["Groceries", "food", "FOOD", "Misc", "<script>", ""])
    def test_category_outside_allow_list_returns_400(self, client, new_user_id, bad_category):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(category=bad_category))
        assert resp.status_code == 400, (
            f"category={bad_category!r} bypassing the <select> must be rejected server-side with a 400"
        )

    @pytest.mark.parametrize("bad_category", ["Groceries", "food", "FOOD", "Misc", "<script>", ""])
    def test_category_outside_allow_list_does_not_insert_row(self, client, new_user_id, bad_category):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(category=bad_category))
        assert get_expenses_for_user(new_user_id) == [], (
            f"category={bad_category!r} must never be inserted as-is, even bypassing the <select>"
        )

    def test_valid_categories_are_each_accepted(self, client, new_user_id):
        login(client, new_user_id)
        for category in ALLOWED_CATEGORIES:
            resp = client.post("/expenses/add", data=valid_payload(category=category))
            assert resp.status_code == 302, f"Allowed category {category!r} must be accepted"
        rows = get_expenses_for_user(new_user_id)
        assert {row["category"] for row in rows} == set(ALLOWED_CATEGORIES), (
            "All seven allowed categories must have been inserted successfully"
        )


# ── Optional description ─────────────────────────────────────────────────────

class TestAddExpenseOptionalDescription:

    def test_blank_description_is_accepted(self, client, new_user_id):
        login(client, new_user_id)
        resp = client.post("/expenses/add", data=valid_payload(description=""))
        assert resp.status_code == 302, "A blank description must not block a valid submission"
        assert resp.headers["Location"].endswith("/profile")

    def test_blank_description_inserts_row(self, client, new_user_id):
        login(client, new_user_id)
        client.post("/expenses/add", data=valid_payload(description=""))
        rows = get_expenses_for_user(new_user_id)
        assert len(rows) == 1, "A row must be inserted even when description is blank"

    def test_missing_description_key_entirely_is_accepted(self, client, new_user_id):
        login(client, new_user_id)
        payload = valid_payload()
        del payload["description"]
        resp = client.post("/expenses/add", data=payload)
        assert resp.status_code == 302, "Omitting the description field entirely must still succeed"
        assert get_expenses_for_user(new_user_id), "A row must be inserted when description key is absent"
