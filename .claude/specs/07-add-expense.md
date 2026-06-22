# Spec: Add Expense

## Overview
Step 7 implements `/expenses/add`, currently a stub that returns the raw
string `"Add expense — coming in Step 7"`. This step turns it into a real
form-backed route so a logged-in user can record a new expense (amount,
category, date, description) and have it appear immediately in their
profile's recent transactions, summary stats, and category breakdown. This
is the first write path into the `expenses` table since seeding — until now
all expense data came from `seed_db()`.

## Depends on
- Step 1: Database setup (`expenses` table schema — `user_id`, `amount`,
  `category`, `date`, `description`)
- Step 4/5: Profile page + backend routes (`get_recent_transactions()`,
  `get_summary_stats()`, `get_category_breakdown()` in
  `database/queries.py` already read from `expenses`; this step adds the
  write side they will reflect)

## Routes
- `GET /expenses/add` — render the empty add-expense form — logged-in
- `POST /expenses/add` — validate and insert a new expense for the current
  user, then redirect to `/profile` — logged-in

Both methods are handled by the same `add_expense()` view, matching the
existing `register()`/`login()` GET+POST pattern in `app.py`.

## Database changes
No schema changes. The existing `expenses` table
(`id, user_id, amount, category, date, description, created_at`) already
supports this feature. This step adds an `insert_expense()` helper in
`database/db.py` — no `ALTER TABLE` needed.

## Templates
- **Create:** `templates/add_expense.html` — form with fields:
  - `amount` — `<input type="number" step="0.01" min="0.01">`
  - `category` — `<select>` with the seven existing categories used by the
    badge CSS (`badge--food`, `--health`, `--transport`, `--entertainment`,
    `--bills`, `--shopping`, `--other`): Food, Health, Transport,
    Entertainment, Bills, Shopping, Other
  - `date` — `<input type="date">`, defaults to today via the route
    (`datetime.now().strftime("%Y-%m-%d")`), not via `<input value>` in the
    template hardcoded
  - `description` — `<input type="text">`, optional
  - Re-uses the `.form-group` / `.form-input` classes already established
    in `register.html` / `profile.html` filter form, and the
    `.auth-error`-style error banner pattern from `register.html` for
    validation errors
- **Modify:** `templates/base.html` has no "Add expense" entry point — add
  a link (`<a href="{{ url_for('add_expense') }}" class="nav-cta">`) to the
  shared navbar, alongside the user name and "Sign out" link, so the page
  is reachable from every logged-in view, not just `/profile`

## Files to change
- `app.py` — replace the `add_expense()` stub:
  - `GET`: render `add_expense.html` with today's date pre-filled and the
    category list
  - `POST`: read `amount`, `category`, `date`, `description` from
    `request.form`, validate, call `insert_expense()`, flash a success
    message, redirect to `url_for('profile')`
  - Require login like `profile()` does (`if not session.get('user_id'):
    return redirect(url_for('login'))`)
- `database/db.py` — add `insert_expense(user_id, amount, category, date,
  description)`, following the existing `create_user()` pattern: open
  connection, parameterized `INSERT`, commit, close
- `templates/base.html` — add an "Add expense" link to the navbar's
  logged-in branch, next to the user name and "Sign out" link

## Files to create
- `templates/add_expense.html`
- `static/css/add_expense.css` — page-specific styles for the form,
  following the CSS-variable convention in `static/css/style.css` (no
  hardcoded hex values)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or string concatenation in
  SQL
- Passwords hashed with werkzeug — not applicable to this feature, no
  password fields involved
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic belongs only in `database/db.py` — `app.py` must not run SQL
  directly
- `amount` must be validated server-side as a positive number before
  insert; reject zero, negative, non-numeric, or missing values with a
  re-rendered form and an error message (400), not a silent fallback
- `category` must be validated against the fixed allow-list of seven
  categories server-side — do not trust the submitted value blindly even
  though it comes from a `<select>`
- `date` must be validated as a real `YYYY-MM-DD` date server-side (reuse
  the same `strptime` validation style as `database/queries.py`'s
  `_is_valid_date`); invalid or missing date is a 400, not a crash
- `description` is optional — store `NULL`/empty if blank, do not require it
- On any validation failure, re-render `add_expense.html` with the
  previously entered values preserved and an error message — never lose
  user input on a failed submit
- Never use raw string returns for this route now that it's implemented

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with amount,
      category, date (defaulted to today), and description fields
- [ ] Submitting valid data creates a new row in `expenses` for the
      logged-in user's `user_id` and redirects to `/profile`
- [ ] After redirect, the new expense appears at the top of "Recent
      Transactions" on the profile page (no date filter applied)
- [ ] After redirect, "Total Spent" and "Transaction Count" on the profile
      page include the new expense
- [ ] After redirect, the category breakdown reflects the new expense's
      category and amount
- [ ] Submitting a negative or zero amount re-renders the form with an
      error and does not insert a row
- [ ] Submitting a non-numeric amount re-renders the form with an error and
      does not insert a row
- [ ] Submitting an invalid or missing date re-renders the form with an
      error and does not insert a row
- [ ] Submitting an empty description succeeds (description is optional)
- [ ] Submitting a category outside the seven allowed values is rejected,
      not inserted as-is
- [ ] `database/db.py` shows only parameterized `?` placeholders in the new
      `insert_expense()` query
- [ ] The navbar has a visible "Add expense" link to `/expenses/add` on
      every logged-in page
