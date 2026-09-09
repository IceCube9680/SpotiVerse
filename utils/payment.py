# utils/payment.py
import os
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict
from info import get_plan_by_id, get_premium_plans
from config import Config
from utils.db import db

logger = logging.getLogger(__name__)

class PaymentOrder:
    def __init__(self, order_id: str, user_id: int, plan_id: str, plan_name: str,
                 amount: int, currency: str = "INR", duration: str = "30d", days: int = 30,
                 provider: str = "manual_upi", status: str = "pending",
                 invoice_payload: str = None, payment_url: str = None):
        self.order_id = order_id
        self.user_id = user_id
        self.plan_id = plan_id
        self.plan_name = plan_name
        self.amount = amount
        self.currency = currency
        self.duration = duration
        self.days = days
        self.provider = provider
        self.status = status  # pending, completed, failed, cancelled
        self.invoice_payload = invoice_payload
        self.payment_url = payment_url

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "amount": self.amount,
            "currency": self.currency,
            "duration": self.duration,
            "days": self.days,
            "provider": self.provider,
            "status": self.status,
            "invoice_payload": self.invoice_payload,
            "payment_url": self.payment_url
        }

class BasePaymentProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    @abstractmethod
    async def create_order(self, user_id: int, plan: dict) -> PaymentOrder:
        pass

    @abstractmethod
    async def verify_payment(self, order_id: str, payment_data: dict) -> bool:
        pass

class ManualUPIPaymentProvider(BasePaymentProvider):
    """
    UPI / Manual Payment Provider: Generates UPI payment details, QR instructions,
    and submits an order for verification.
    """
    def __init__(self, upi_id: str = None):
        self.upi_id = upi_id or getattr(Config, "PAYMENT_UPI_ID", "icecube@upi")

    @property
    def provider_id(self) -> str:
        return "manual_upi"

    @property
    def display_name(self) -> str:
        return "UPI / Manual Transfer"

    def create_invoice(self, order: PaymentOrder) -> dict:
        return {
            "provider": "manual_upi",
            "upi_id": self.upi_id,
            "amount": order.amount,
            "currency": order.currency,
            "payment_url": order.payment_url or f"upi://pay?pa={self.upi_id}&pn=SpotiVerse&am={order.amount}&cu=INR&tn=SpotiVerse_{order.order_id}"
        }

    async def create_order(self, user_id: int, plan: dict) -> PaymentOrder:
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        amount = plan.get("price", 99)
        plan_name = plan.get("name", "Premium Plan")
        
        # Format UPI intent URI
        upi_uri = f"upi://pay?pa={self.upi_id}&pn=SpotiVerse&am={amount}&cu=INR&tn=SpotiVerse_{order_id}"

        order = PaymentOrder(
            order_id=order_id,
            user_id=user_id,
            plan_id=plan.get("id"),
            plan_name=plan_name,
            amount=amount,
            currency=plan.get("currency", "INR"),
            duration=plan.get("duration", "30d"),
            days=plan.get("days", 30),
            provider=self.provider_id,
            status="pending",
            payment_url=upi_uri
        )
        return order

    async def verify_payment(self, order_id: str, payment_data: dict) -> bool:
        # Manual verification must be performed by admin
        return False

class TelegramPaymentProvider(BasePaymentProvider):
    """
    Telegram Payments Native Gateway: Generates native Telegram invoice parameters.
    """
    @property
    def provider_id(self) -> str:
        return "telegram_payments"

    @property
    def display_name(self) -> str:
        return "Telegram Payments"

    async def create_order(self, user_id: int, plan: dict) -> PaymentOrder:
        order_id = f"TG-{uuid.uuid4().hex[:8].upper()}"
        amount = plan.get("price", 99)
        plan_name = plan.get("name", "Premium Plan")

        order = PaymentOrder(
            order_id=order_id,
            user_id=user_id,
            plan_id=plan.get("id"),
            plan_name=plan_name,
            amount=amount,
            currency=plan.get("currency", "INR"),
            duration=plan.get("duration", "30d"),
            days=plan.get("days", 30),
            provider=self.provider_id,
            status="pending",
            invoice_payload=f"spotiverse_premium_{order_id}"
        )
        return order

    async def verify_payment(self, order_id: str, payment_data: dict) -> bool:
        # Verified via successful pre_checkout_query and successful_payment message in Telegram
        return bool(payment_data.get("is_valid", False))

class PaymentManager:
    """
    Orchestrates payment providers and orders.
    Prevents automatic premium granting on button clicks.
    """
    def __init__(self):
        self._providers: Dict[str, BasePaymentProvider] = {
            "manual_upi": ManualUPIPaymentProvider(),
            "upi_manual": ManualUPIPaymentProvider(),
            "telegram_payments": TelegramPaymentProvider()
        }
        self._orders: Dict[str, PaymentOrder] = {}

    def get_provider(self, provider_id: str) -> Optional[BasePaymentProvider]:
        return self._providers.get(provider_id)

    def get_default_provider(self) -> BasePaymentProvider:
        if getattr(Config, "PAYMENT_PROVIDER_TOKEN", None):
            return self._providers["telegram_payments"]
        return self._providers["manual_upi"]

    def create_order(self, user_id: int, plan_id: str, provider_id: str = None) -> PaymentOrder:
        """Synchronously create and register a pending payment order"""
        plan = get_plan_by_id(plan_id) or {"id": plan_id, "name": plan_id.title(), "price": 99, "currency": "INR", "duration": "30d", "days": 30}
        provider = self.get_provider(provider_id) or self.get_default_provider()
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order = PaymentOrder(
            order_id=order_id,
            user_id=user_id,
            plan_id=plan.get("id", plan_id),
            plan_name=plan.get("name", "Premium Plan"),
            amount=plan.get("price", 99),
            currency=plan.get("currency", "INR"),
            duration=plan.get("duration", "30d"),
            days=plan.get("days", 30),
            provider=provider.provider_id,
            status="pending"
        )
        self._orders[order.order_id] = order
        return order

    async def initiate_plan_purchase(self, user_id: int, plan_id: str, provider_id: str = None) -> Optional[PaymentOrder]:
        """
        Initiate plan purchase and generate an order.
        DOES NOT grant premium!
        """
        plan = get_plan_by_id(plan_id)
        if not plan:
            return None

        provider = self.get_provider(provider_id) if provider_id else self.get_default_provider()
        if not provider:
            provider = self.get_default_provider()

        order = await provider.create_order(user_id, plan)
        self._orders[order.order_id] = order
        return order

    def get_order(self, order_id: str) -> Optional[PaymentOrder]:
        return self._orders.get(order_id)

    def complete_verified_order(self, order_id: str, admin_id: int = None) -> bool:
        """
        Activates premium ONLY after payment verification or admin confirmation.
        """
        order = self.get_order(order_id)
        if not order or order.status == "completed":
            return False

        order.status = "completed"
        # Grant premium in DB
        db.add_premium(
            user_id=order.user_id,
            days=order.days,
            plan_name=order.plan_name,
            admin_id=admin_id
        )
        logger.info(f"Payment verified: Granted {order.plan_name} to user {order.user_id} (Order {order_id})")
        return True

payment_manager = PaymentManager()
