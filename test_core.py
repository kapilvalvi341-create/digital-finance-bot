import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from datetime import date
from decimal import Decimal
import pytest
from app import create_app
import services as svc


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    return app.test_client()


def register(c, email="a@x.com"):
    return c.post("/api/auth/register", json={"name": "A", "email": email, "password": "password123"})


TODAY = date.today().isoformat()


# ---- calculations ----
def test_savings_math():
    net, rate = svc.savings_figures(Decimal("50000"), Decimal("32500.50"))
    assert net == Decimal("17499.50") and rate == Decimal("35.00")

def test_zero_income_and_negative_savings():
    net, rate = svc.savings_figures(Decimal("0"), Decimal("100"))
    assert net == Decimal("-100.00") and rate is None
    assert svc.savings_figures(Decimal("100"), Decimal("150"))[1] == Decimal("-50.00")

def test_budget_utilization_and_status():
    assert svc.utilization(Decimal("80"), Decimal("100")) == Decimal("80.00")
    assert svc.utilization(Decimal("5"), Decimal("0")) is None
    assert svc.budget_status(Decimal("79.99")) == "ok"
    assert svc.budget_status(Decimal("80")) == "warning"
    assert svc.budget_status(Decimal("100.01")) == "over"

def test_no_float_error():
    assert svc.q(Decimal("0.1") + Decimal("0.2")) == Decimal("0.30")


# ---- auth ----
def test_auth_required(client):
    for p in ["/api/income", "/api/expenses", "/api/dashboard", "/api/auth/me"]:
        assert client.get(p).status_code == 401

def test_register_login_logout(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "password123"}).status_code == 200


# ---- CRUD + dashboard ----
def test_crud_and_dashboard(client):
    register(client)
    r = client.post("/api/income", json={"amount": "50000", "source": "Salary", "date": TODAY})
    assert r.status_code == 201
    e = client.post("/api/expenses", json={"amount": "1250.75", "category": "Food", "date": TODAY, "payment_method": "UPI"})
    eid = e.get_json()["data"]["id"]
    d = client.get("/api/dashboard").get_json()["data"]
    assert d["total_income"] == "50000.00" and d["total_expenses"] == "1250.75"
    assert d["net_savings"] == "48749.25" and d["savings_rate"] == "97.50"
    client.put(f"/api/expenses/{eid}", json={"amount": "2000", "category": "Food", "date": TODAY})
    assert client.get("/api/dashboard").get_json()["data"]["total_expenses"] == "2000.00"
    assert client.delete(f"/api/expenses/{eid}").status_code == 200
    assert client.get("/api/dashboard").get_json()["data"]["total_expenses"] == "0.00"

def test_validation(client):
    register(client)
    assert client.post("/api/income", json={"amount": "-5", "source": "Salary", "date": TODAY}).status_code == 422
    assert client.post("/api/income", json={"amount": "abc", "source": "Nope", "date": "bad"}).status_code == 422
    assert client.post("/api/expenses", json={"amount": "NaN", "category": "", "date": TODAY}).status_code == 422

def test_user_isolation(client):
    register(client, "a@x.com")
    eid = client.post("/api/expenses", json={"amount": "10", "category": "Food", "date": TODAY}).get_json()["data"]["id"]
    client.post("/api/auth/logout")
    register(client, "b@x.com")
    assert client.get("/api/expenses").get_json()["data"]["items"] == []
    assert client.put(f"/api/expenses/{eid}", json={"amount": "1", "category": "Food", "date": TODAY}).status_code == 404
    assert client.delete(f"/api/expenses/{eid}").status_code == 404
    assert client.get("/api/dashboard").get_json()["data"]["total_expenses"] == "0.00"
