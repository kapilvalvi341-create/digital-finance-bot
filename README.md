# FinBot – Backend (Phase 1)

**Implemented & tested:** registration/login/logout (hashed passwords, HTTP-only session cookie), income and expense CRUD with
filtering/search/sort, per-user data isolation, Decimal-based dashboard calculations (income, expenses, net savings, savings rate,
category breakdown, 6-month trend, budget progress if budget rows exist, recent transactions), plus all SQLAlchemy models.

**Not yet implemented:** React frontend, budget/goal/report/settings endpoints, AI advisor, CSV export, demo-data mode.
(Models for Budget, SavingsGoal, SavingsContribution and ChatMessage exist, but have no routes yet.)

## Run
```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then set SECRET_KEY
python app.py             # http://localhost:5000, tables auto-created in finbot.db
pytest -q                 # run tests
```
Frontend requests must use `credentials: "include"`, and `FRONTEND_ORIGIN` must match the frontend URL.

## API (JSON: `{success, data}` or `{success:false, error, details}`)
`POST /api/auth/register|login|logout`, `GET /api/auth/me`, `GET /api/meta`,
`GET|POST /api/income`, `PUT|DELETE /api/income/<id>`, same for `/api/expenses`,
`GET /api/dashboard?period=this_month|last_month|custom&start=&end=`.
Money is returned as decimal strings. Savings rate is `null` when income is 0.

## Notes
- Schema is created with `db.create_all()`. For schema changes later, add Flask-Migrate (`flask db init/migrate/upgrade`).
- State-changing endpoints rely on SameSite=Lax cookies + JSON bodies; add CSRF tokens before any production deployment.
