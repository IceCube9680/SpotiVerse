import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta, timezone
from info import get_premium_plans, get_plan_by_id, parse_duration_to_timedelta, DEFAULT_PREMIUM_PLANS
from utils.db import Database, _fallback_store, _parse_datetime
from utils.payment import PaymentManager, ManualUPIPaymentProvider, TelegramPaymentProvider, PaymentOrder
from utils.feature_gates import FeatureGate

class TestPremiumSystem(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(connect=False)
        self.db.available = False
        _fallback_store["users"].clear()
        _fallback_store["bot_settings"].clear()
        _fallback_store["provider_settings"].clear()

    def tearDown(self):
        self.db.close()

    def test_duration_parsing(self):
        self.assertEqual(parse_duration_to_timedelta("7d"), timedelta(days=7))
        self.assertEqual(parse_duration_to_timedelta("30d"), timedelta(days=30))
        self.assertEqual(parse_duration_to_timedelta("90d"), timedelta(days=90))
        self.assertEqual(parse_duration_to_timedelta("180d"), timedelta(days=180))
        self.assertEqual(parse_duration_to_timedelta("1y"), timedelta(days=365))
        self.assertEqual(parse_duration_to_timedelta("lifetime"), timedelta(days=36500))
        self.assertEqual(parse_duration_to_timedelta("30"), timedelta(days=30))

    def test_premium_plans_configuration_and_discounts(self):
        plans = get_premium_plans()
        self.assertTrue(len(plans) >= 3)
        plan_ids = [p["id"] for p in plans]
        self.assertIn("1_month", plan_ids)
        self.assertIn("3_months", plan_ids)
        self.assertIn("6_months", plan_ids)

        p1 = get_plan_by_id("1_month")
        self.assertIsNotNone(p1)
        self.assertEqual(p1["price"], 99)
        self.assertEqual(p1["duration"], "30d")

        p3 = get_plan_by_id("3_months")
        self.assertIsNotNone(p3)
        self.assertEqual(p3["price"], 249)
        self.assertTrue("OFF" in p3.get("badge", "") or "Popular" in p3.get("badge", ""))

    def test_add_and_remove_premium(self):
        uid = 999111
        # Add 30 days
        self.db.add_premium(uid, 30, plan_name="1 Month")
        self.assertTrue(self.db.is_premium(uid))

        user = self.db.get_user(uid)
        self.assertTrue(user.get("premium"))
        self.assertEqual(user.get("premium_plan"), "1 Month")
        self.assertIsNotNone(user.get("premium_until"))

        # Remove premium
        self.db.remove_premium(uid)
        self.assertFalse(self.db.is_premium(uid))
        user_after = self.db.get_user(uid)
        self.assertFalse(user_after.get("premium"))
        self.assertIsNone(user_after.get("premium_until"))

    def test_lifetime_premium(self):
        uid = 999222
        self.db.add_premium(uid, "lifetime", plan_name="Lifetime VIP")
        self.assertTrue(self.db.is_premium(uid))
        user = self.db.get_user(uid)
        self.assertTrue(user.get("lifetime_premium"))
        self.assertTrue(self.db.is_premium(uid))

    def test_expired_premium_behavior(self):
        uid = 999333
        # Set premium expired yesterday
        yesterday = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        self.db.update_user(uid, {
            "premium": True,
            "premium_until": yesterday.isoformat(),
            "lifetime_premium": False
        })

        # is_premium should evaluate to False and reset status
        self.assertFalse(self.db.is_premium(uid))
        user = self.db.get_user(uid)
        self.assertFalse(user.get("premium"))

    def test_payment_architecture_separated_from_activation(self):
        # Selecting a plan must NOT grant premium immediately
        uid = 999444
        self.assertFalse(self.db.is_premium(uid))

        pm = PaymentManager()
        order = pm.create_order(uid, "1_month")
        self.assertIsInstance(order, PaymentOrder)
        self.assertEqual(order.user_id, uid)
        self.assertEqual(order.plan_id, "1_month")
        self.assertEqual(order.status, "pending")

        # Crucial security assertion: User is still NOT premium!
        self.assertFalse(self.db.is_premium(uid))

        # Admin or verified webhook must activate
        self.db.add_premium(uid, 30, plan_name=order.plan_name)
        self.assertTrue(self.db.is_premium(uid))

    def test_manual_upi_payment_provider(self):
        provider = ManualUPIPaymentProvider(upi_id="spotiverse@upi")
        order = PaymentOrder(
            order_id="ORD-12345",
            user_id=123,
            plan_id="1_month",
            plan_name="1 Month",
            amount=99,
            currency="INR",
            duration="30d"
        )
        invoice = provider.create_invoice(order)
        self.assertEqual(invoice["provider"], "manual_upi")
        self.assertIn("spotiverse@upi", invoice["upi_id"])
        self.assertEqual(invoice["amount"], 99)

if __name__ == "__main__":
    unittest.main()
