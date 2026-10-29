from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()
Money = db.Numeric(12, 2)  # exact decimal; read back as decimal.Decimal


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    currency = db.Column(db.String(3), default="INR", nullable=False)

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)


class Income(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    source = db.Column(db.String(40), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.String(255), default="")


class Expense(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)
    payment_method = db.Column(db.String(20), default="Cash")
    date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.String(255), default="")


class Budget(db.Model, TimestampMixin):
    """category=None means the overall budget for that month ('YYYY-MM')."""
    __table_args__ = (db.UniqueConstraint("user_id", "month", "category"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    month = db.Column(db.String(7), nullable=False)
    category = db.Column(db.String(40), nullable=True)
    limit = db.Column(Money, nullable=False)


class SavingsGoal(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    target_amount = db.Column(Money, nullable=False)
    target_date = db.Column(db.Date)
    completed = db.Column(db.Boolean, default=False, nullable=False)
    contributions = db.relationship("SavingsContribution", backref="goal", cascade="all, delete-orphan")


class SavingsContribution(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey("savings_goal.id"), nullable=False, index=True)
    amount = db.Column(Money, nullable=False)  # negative = withdrawal
    date = db.Column(db.Date, nullable=False, default=date.today)


class ChatMessage(db.Model, TimestampMixin):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    role = db.Column(db.String(10), nullable=False)  # user | assistant
    content = db.Column(db.Text, nullable=False)
