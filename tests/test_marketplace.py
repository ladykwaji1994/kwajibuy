import hashlib
import hmac
import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import main


class MarketplaceFlowTests(unittest.TestCase):
    def setUp(self):
        self.database_directory = tempfile.TemporaryDirectory()
        main.DB_PATH = os.path.join(self.database_directory.name, "test.sqlite3")
        os.environ["KWAJIBUY_ENABLE_DEMO_ACCOUNTS"] = "1"
        os.environ["KWAJIBUY_ADMIN_TOKEN"] = "test-service-token"
        os.environ["KWAJIBUY_PAYSTACK_SECRET_KEY"] = "test-paystack-secret"
        main.initialize_database()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.database_directory.cleanup()

    def register(self, email, role="shopper", store_name=""):
        return self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "Coursework-pass-123",
                "full_name": "Coursework User",
                "role": role,
                "store_name": store_name,
            },
        )

    def test_shop_user_login_logout_and_order_history(self):
        self.assertEqual(self.register("buyer@example.com").status_code, 200)
        response = self.client.post(
            "/api/auth/login",
            json={"email": "buyer@example.com", "password": "Coursework-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        self.assertEqual(
            self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).json()["role"],
            "shopper",
        )
        order_id, total = main.record_order(
            "Coursework User", "08000000000", "Lagos", {"phone-01": 2}, email="buyer@example.com"
        )
        self.assertEqual(total, 859800)
        self.assertEqual(main.list_orders(customer_email="buyer@example.com")[0]["order_id"], order_id)
        self.assertEqual(
            self.client.post("/api/auth/logout", headers={"Authorization": "Bearer " + token}).status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code,
            401,
        )

    def test_public_signup_cannot_grant_admin_role(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": "self-admin@example.com",
                "password": "Coursework-pass-123",
                "full_name": "Self Admin",
                "role": "admin",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/admin/orders").status_code, 401)

    def test_seller_owns_catalog_and_can_manage_listing(self):
        seller = self.register("seller@example.com", role="seller", store_name="Aso Studio").json()["user"]
        self.assertEqual(seller["seller_status"], "pending")
        with self.assertRaises(ValueError):
            main.create_seller_product(seller["id"], "Woven Tote", "Fashion", 12000, 15000)
        main.set_seller_status(seller["id"], "approved")
        product = main.create_seller_product(seller["id"], "Woven Tote", "Fashion", 12000, 15000)
        self.assertEqual(product["seller"], "Aso Studio")
        self.assertEqual(main.update_seller_product(seller["id"], product["id"], "Market Tote", "Fashion", 13000, 16000)["price"], 13000)
        other_seller = self.register("other@example.com", role="seller", store_name="Other Store").json()["user"]
        main.set_seller_status(other_seller["id"], "approved")
        with self.assertRaises(ValueError):
            main.update_seller_product(other_seller["id"], product["id"], "Taken", "Fashion", 100, 150)
        main.deactivate_seller_product(seller["id"], product["id"])
        self.assertIsNone(main.get_product(product["id"]))

    def test_seller_catalog_product_can_be_ordered(self):
        seller = self.register("maker@example.com", role="seller", store_name="Local Maker").json()["user"]
        main.set_seller_status(seller["id"], "approved")
        product = main.create_seller_product(seller["id"], "Woven Basket", "Home", 7000, 9000)
        order_id, total = main.record_order("Buyer", "0800", "Lagos", {product["id"]: 1})
        self.assertEqual(total, 7000)
        self.assertEqual(main.list_orders()[0]["order_id"], order_id)

    def test_paystack_webhook_checks_signature_and_is_idempotent(self):
        self.register("paying@example.com")
        order_id, total = main.record_order(
            "Coursework User", "0800", "Lagos", {"phone-01": 1}, "paystack", "paying@example.com"
        )
        event = {
            "event": "charge.success",
            "data": {"reference": order_id, "status": "success", "amount": total * 100, "currency": "NGN"},
        }
        body = json.dumps(event).encode("utf-8")
        signature = hmac.new(b"test-paystack-secret", body, hashlib.sha512).hexdigest()
        self.assertEqual(
            self.client.post("/api/payments/paystack/webhook", content=body, headers={"x-paystack-signature": "bad"}).status_code,
            401,
        )
        headers = {"x-paystack-signature": signature}
        self.assertEqual(self.client.post("/api/payments/paystack/webhook", content=body, headers=headers).json()["status"], "processed")
        self.assertEqual(self.client.post("/api/payments/paystack/webhook", content=body, headers=headers).json()["status"], "already_processed")


if __name__ == "__main__":
    unittest.main()