"""Business logic: validation and financial calculations (no Flask request objects)."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from models import db, Income, Expense, Budget

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("1000000000")
INCOME_SOURCES = ["Salary", "Freelance", "Business", "Other"]
DEFAULT_CATEGORIES = ["Food", "Rent", "Transport", "Education", "Healthcare",
                      "Shopping", "Entertainment", "Utilities", "Subscriptions", "Other"]
PAYMENT_METHODS = ["Cash", "UPI", "Card", "Bank Transfer", "Other"]


class ValidationError(Exception):
    def __init__(self, errors): self.errors = errors


def q(x): return Decimal(x).quantize(CENT)


def validate_txn(data, kind):
    """Return cleaned dict for an 'income' or 'expense' payload, or raise ValidationError."""
    errors, out = {}, {}
    try:
        amt = q(Decimal(str(data.get("amount"))))
        if amt <= 0 or amt > MAX_AMOUNT: errors["amount"] = "Amount must be greater than 0 and under 1,000,000,000."
        out["amount"] = amt
    except (InvalidOperation, TypeError, ValueError):
        errors["amount"] = "Amount must be a valid number."
    try:
        out["date"] = date.fromisoformat(str(data.get("date")))
    except ValueError:
        errors["date"] = "Date must be YYYY-MM-DD."
    desc = (data.get("description") or "").strip()
    if len(desc) > 255: errors["description"] = "Description is too long (max 255)."
    out["description"] = desc
    if kind == "income":
        src = data.get("source")
        if src not in INCOME_SOURCES: errors["source"] = f"Source must be one of {INCOME_SOURCES}."
        out["source"] = src
    else:
        cat = (data.get("category") or "").strip()
        if not 1 <= len(cat) <= 40: errors["category"] = "Category is required (max 40 chars)."
        out["category"] = cat
        pm = data.get("payment_method") or "Cash"
        if pm not in PAYMENT_METHODS: errors["payment_method"] = f"Payment method must be one of {PAYMENT_METHODS}."
        out["payment_method"] = pm
    if errors: raise ValidationError(errors)
    return out


def month_bounds(d):
    return d.replace(day=1), d.replace(day=monthrange(d.year, d.month)[1])


def add_months(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def resolve_period(period, start=None, end=None, today=None):
    today = today or date.today()
    if period == "last_month":
        return month_bounds(add_months(today, -1))
    if period == "custom":
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        if s > e: raise ValidationError({"range": "Start date must not be after end date."})
        return s, e
    return month_bounds(today)


def _sum(rows): return sum((r.amount for r in rows), Decimal("0.00"))


def _in_range(model, uid, s, e):
    return model.query.filter(model.user_id == uid, model.date >= s, model.date <= e)


def savings_figures(income, expenses):
    net = q(income - expenses)
    rate = q(net / income * 100) if income > 0 else None  # None = undefined with zero income
    return net, rate


def utilization(spent, limit):
    return q(spent / limit * 100) if limit and limit > 0 else None


def budget_status(util):
    if util is None: return "no_budget"
    return "over" if util > 100 else "warning" if util >= 80 else "ok"


def dashboard(uid, s, e):
    inc_rows = _in_range(Income, uid, s, e).all()
    exp_rows = _in_range(Expense, uid, s, e).all()
    income, expenses = _sum(inc_rows), _sum(exp_rows)
    net, rate = savings_figures(income, expenses)

    by_cat = {}
    for r in exp_rows: by_cat[r.category] = by_cat.get(r.category, Decimal("0.00")) + r.amount

    month = s.strftime("%Y-%m")
    budgets = Budget.query.filter_by(user_id=uid, month=month).all()
    progress, overall = [], None
    for b in budgets:
        spent = expenses if b.category is None else by_cat.get(b.category, Decimal("0.00"))
        u = utilization(spent, b.limit)
        item = {"category": b.category, "limit": str(b.limit), "spent": str(spent),
                "remaining": str(q(b.limit - spent)), "utilization": None if u is None else str(u),
                "status": budget_status(u)}
        if b.category is None: overall = item
        else: progress.append(item)

    trend = []
    for i in range(5, -1, -1):  # last six months, ending with the current month
        ms, me = month_bounds(add_months(date.today(), -i))
        mi, mx = _sum(_in_range(Income, uid, ms, me).all()), _sum(_in_range(Expense, uid, ms, me).all())
        trend.append({"month": ms.strftime("%Y-%m"), "income": str(mi), "expenses": str(mx), "net_savings": str(q(mi - mx))})

    recent = sorted([("income", r) for r in inc_rows] + [("expense", r) for r in exp_rows],
                    key=lambda t: (t[1].date, t[1].id), reverse=True)[:8]
    return {
        "range": {"start": s.isoformat(), "end": e.isoformat()},
        "total_income": str(income), "total_expenses": str(expenses),
        "net_savings": str(net), "savings_rate": None if rate is None else str(rate),
        "remaining_budget": overall["remaining"] if overall else None,
        "category_breakdown": [{"category": k, "amount": str(v)} for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])],
        "budget_progress": progress, "overall_budget": overall, "trend": trend,
        "recent_transactions": [{"type": t, **serialize(r, t)} for t, r in recent],
    }


def serialize(r, kind):
    d = {"id": r.id, "amount": str(r.amount), "date": r.date.isoformat(), "description": r.description}
    if kind == "income": d["source"] = r.source
    else: d.update(category=r.category, payment_method=r.payment_method)
    return d
