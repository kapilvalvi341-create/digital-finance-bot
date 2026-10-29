import os
import warnings
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from sqlalchemy.exc import SAWarning

import services as svc
from models import db, User, Income, Expense

warnings.filterwarnings("ignore", message=".*does \\*not\\* support Decimal.*", category=SAWarning)
load_dotenv()


def ok(data=None, status=200): return jsonify({"success": True, "data": data}), status
def fail(msg, status=400, errors=None): return jsonify({"success": False, "error": msg, "details": errors}), status


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        uid = session.get("user_id")
        if not uid or not db.session.get(User, uid):
            return fail("Authentication required.", 401)
        return f(uid, *a, **kw)
    return wrapper


def create_app(config=None):
    app = Flask(__name__)
    secret = os.getenv("SECRET_KEY")
    if not secret and not (config or {}).get("TESTING"):
        raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and set it.")
    app.config.update(SECRET_KEY=secret or "test-only", SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///finbot.db"),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    app.config.update(config or {})
    CORS(app, origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")], supports_credentials=True)
    db.init_app(app)
    with app.app_context(): db.create_all()

    @app.errorhandler(svc.ValidationError)
    def _val(e): return fail("Validation failed.", 422, e.errors)

    @app.errorhandler(404)
    def _404(e): return fail("Not found.", 404)

    # ---------- auth ----------
    @app.post("/api/auth/register")
    def register():
        d = request.get_json(silent=True) or {}
        name, email, pw = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower(), d.get("password") or ""
        errs = {}
        if not name: errs["name"] = "Name is required."
        if "@" not in email or len(email) > 120: errs["email"] = "A valid email is required."
        if len(pw) < 8: errs["password"] = "Password must be at least 8 characters."
        if errs: return fail("Validation failed.", 422, errs)
        if User.query.filter_by(email=email).first(): return fail("Email already registered.", 409)
        u = User(name=name, email=email); u.set_password(pw)
        db.session.add(u); db.session.commit()
        session.clear(); session["user_id"] = u.id
        return ok({"id": u.id, "name": u.name, "email": u.email, "currency": u.currency}, 201)

    @app.post("/api/auth/login")
    def login():
        d = request.get_json(silent=True) or {}
        u = User.query.filter_by(email=(d.get("email") or "").strip().lower()).first()
        if not u or not u.check_password(d.get("password") or ""): return fail("Invalid email or password.", 401)
        session.clear(); session["user_id"] = u.id
        return ok({"id": u.id, "name": u.name, "email": u.email, "currency": u.currency})

    @app.post("/api/auth/logout")
    def logout():
        session.clear(); return ok()

    @app.get("/api/auth/me")
    @login_required
    def me(uid):
        u = db.session.get(User, uid)
        return ok({"id": u.id, "name": u.name, "email": u.email, "currency": u.currency})

    # ---------- income / expense CRUD (always scoped to the logged-in user) ----------
    def crud(model, kind, path):
        def list_(uid):
            qy = model.query.filter_by(user_id=uid)
            a = request.args
            try:
                if a.get("start"): qy = qy.filter(model.date >= svc.date.fromisoformat(a["start"]))
                if a.get("end"): qy = qy.filter(model.date <= svc.date.fromisoformat(a["end"]))
            except ValueError:
                return fail("start/end must be YYYY-MM-DD.", 422)
            if kind == "income" and a.get("source"): qy = qy.filter(model.source == a["source"])
            if kind == "expense":
                if a.get("category"): qy = qy.filter(model.category == a["category"])
                if a.get("q"): qy = qy.filter(model.description.ilike(f"%{a['q']}%"))
            sort = a.get("sort", "date_desc")
            col = {"date": model.date, "amount": model.amount}.get(sort.split("_")[0], model.date)
            qy = qy.order_by(col.asc() if sort.endswith("_asc") else col.desc(), model.id.desc())
            rows = qy.all()
            return ok({"items": [svc.serialize(r, kind) for r in rows], "total": str(svc.q(sum((r.amount for r in rows), svc.Decimal(0))))})

        def create(uid):
            row = model(user_id=uid, **svc.validate_txn(request.get_json(silent=True) or {}, kind))
            db.session.add(row); db.session.commit()
            return ok(svc.serialize(row, kind), 201)

        def own(uid, rid):
            return model.query.filter_by(id=rid, user_id=uid).first()  # other users' rows look like 404

        def update(uid, rid):
            row = own(uid, rid)
            if not row: return fail("Not found.", 404)
            for k, v in svc.validate_txn(request.get_json(silent=True) or {}, kind).items(): setattr(row, k, v)
            db.session.commit(); return ok(svc.serialize(row, kind))

        def delete(uid, rid):
            row = own(uid, rid)
            if not row: return fail("Not found.", 404)
            db.session.delete(row); db.session.commit(); return ok()

        app.add_url_rule(path, f"{kind}_list", login_required(list_), methods=["GET"])
        app.add_url_rule(path, f"{kind}_create", login_required(create), methods=["POST"])
        app.add_url_rule(path + "/<int:rid>", f"{kind}_update", login_required(update), methods=["PUT"])
        app.add_url_rule(path + "/<int:rid>", f"{kind}_delete", login_required(delete), methods=["DELETE"])

    crud(Income, "income", "/api/income")
    crud(Expense, "expense", "/api/expenses")

    @app.get("/api/meta")
    def meta():
        return ok({"income_sources": svc.INCOME_SOURCES, "default_categories": svc.DEFAULT_CATEGORIES,
                   "payment_methods": svc.PAYMENT_METHODS})

    @app.get("/api/dashboard")
    @login_required
    def dash(uid):
        a = request.args
        try: s, e = svc.resolve_period(a.get("period", "this_month"), a.get("start"), a.get("end"))
        except (ValueError, TypeError): return fail("Custom range needs valid start and end (YYYY-MM-DD).", 422)
        return ok(svc.dashboard(uid, s, e))

    return app


if __name__ == "__main__":
    create_app().run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
