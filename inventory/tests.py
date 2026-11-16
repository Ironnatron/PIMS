from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BatchForm, ProductForm
from .models import Batch, Product, StockAdjustment, Supplier
from .services import adjust_stock


class InventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="staff", password="Test-only-long-password!57", is_staff=True,
        )
        cls.product = Product.objects.create(sku="MED-001", name="Test medicine", reorder_level=10)
        cls.supplier = Supplier.objects.create(name="Test supplier")
        cls.today = timezone.localdate()
        cls.batch = Batch.objects.create(
            product=cls.product, supplier=cls.supplier, batch_number="B001",
            received_date=cls.today, expiry_date=cls.today + timedelta(days=60),
            purchase_price="12.50", selling_price="15.00",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def adjust(self, change, **kwargs):
        return adjust_stock(
            batch_id=self.batch.pk, change=change, reason=kwargs.get("reason", "Stock receipt"),
            user=self.user,
        )

    def batch_data(self, **kwargs):
        data = {
            "product": self.product.pk, "supplier": self.supplier.pk,
            "batch_number": "B002", "received_date": self.today,
            "expiry_date": self.today + timedelta(days=100),
            "purchase_price": "10.00", "selling_price": "15.00",
        }
        data.update(kwargs)
        return data

    def test_staff_access_required_for_inventory(self):
        for name in ["dashboard", "product_list", "supplier_list", "batch_list"]:
            self.client.logout()
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
            nonstaff = get_user_model().objects.get_or_create(username="nonstaff")[0]
            self.client.force_login(nonstaff)
            self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        response = self.client.post(reverse("product_add"), {"name": "Unauthorized"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Product.objects.count(), 1)

    def test_stock_receipt_and_removal_record_balance_and_actor(self):
        first = self.adjust(20, reason="Initial receipt")
        second = self.adjust(-7, reason="Damaged stock disposal")
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 13)
        self.assertEqual(first.resulting_quantity, 20)
        self.assertEqual(second.resulting_quantity, 13)
        self.assertEqual(second.user, self.user)
        self.assertEqual(StockAdjustment.objects.count(), 2)

    def test_invalid_changes_do_not_mutate_stock_or_history(self):
        self.adjust(5)
        for change, reason in [(-6, "Too many"), (0, "Zero"), (1, "  "), (2147483647, "Overflow")]:
            with self.assertRaises(ValidationError):
                self.adjust(change, reason=reason)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 5)
        self.assertEqual(StockAdjustment.objects.count(), 1)

    def test_ledger_failure_rolls_back_quantity(self):
        with patch("inventory.services.StockAdjustment.objects.create", side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.adjust(10)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 0)

    def test_expired_batch_blocks_receipt_but_allows_disposal(self):
        self.adjust(10)
        Batch.objects.filter(pk=self.batch.pk).update(
            received_date=self.today - timedelta(days=100), expiry_date=self.today - timedelta(days=1),
        )
        with self.assertRaisesMessage(ValidationError, "expired"):
            self.adjust(1)
        self.adjust(-10, reason="Expired stock disposal")
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity, 0)

    def test_inactive_product_or_supplier_blocks_receipt(self):
        for model, record in [(Product, self.product), (Supplier, self.supplier)]:
            model.objects.filter(pk=record.pk).update(is_active=False)
            with self.assertRaisesMessage(ValidationError, "Reactivate"):
                self.adjust(1)
            model.objects.filter(pk=record.pk).update(is_active=True)

    def test_dashboard_stock_and_expiry_boundaries(self):
        self.adjust(10)
        for number, expiry, quantity in [
            ("expired", self.today - timedelta(days=1), 25),
            ("today", self.today, 3),
            ("ninety", self.today + timedelta(days=90), 2),
            ("later", self.today + timedelta(days=91), 4),
        ]:
            Batch.objects.create(
                product=self.product, supplier=self.supplier, batch_number=number,
                received_date=self.today - timedelta(days=100), expiry_date=expiry,
                quantity=quantity, purchase_price=1, selling_price=2,
            )
        empty = Product.objects.create(sku="EMPTY", name="No stock")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["expired_count"], 1)
        self.assertEqual(response.context["expiring_count"], 3)
        self.assertEqual(response.context["low_count"], 1)
        self.assertEqual(response.context["low_products"][0], empty)
        detail = self.client.get(reverse("product_detail", args=[self.product.pk]))
        self.assertEqual(detail.context["product"].stock, 19)
        Supplier.objects.filter(pk=self.supplier.pk).update(is_active=False)
        self.assertEqual(
            self.client.get(reverse("product_detail", args=[self.product.pk])).context["product"].stock, 0,
        )

    def test_product_create_edit_search_and_delete_unused(self):
        response = self.client.post(reverse("product_add"), {
            "sku": " med-002 ", "name": "New medicine", "kind": "medicine",
            "unit": "bottle", "reorder_level": 5, "is_active": "on",
        })
        product = Product.objects.get(sku="MED-002")
        self.assertRedirects(response, reverse("product_detail", args=[product.pk]))
        response = self.client.post(reverse("product_edit", args=[product.pk]), {
            "sku": product.sku, "name": "Edited medicine", "kind": "medicine",
            "unit": "bottle", "reorder_level": 7, "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, "Edited medicine")
        response = self.client.get(reverse("product_list"), {"q": "MED-002"})
        self.assertEqual(list(response.context["products"]), [product])
        self.assertEqual(self.client.post(reverse("product_delete", args=[product.pk])).status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_product_form_rejects_duplicate_sku_and_nonmedicine_prescription(self):
        for sku, kind, rx in [("med-001", "medicine", False), ("NEW", "other", True)]:
            form = ProductForm(data={
                "sku": sku, "name": "Test", "kind": kind, "unit": "box",
                "reorder_level": 1, "requires_prescription": rx,
            })
            self.assertFalse(form.is_valid())
            self.assertIn("sku" if kind == "medicine" else "requires_prescription", form.errors)

    def test_stock_unit_cannot_change_after_batches_exist(self):
        form = ProductForm(instance=self.product, data={
            "sku": self.product.sku, "name": self.product.name, "kind": "medicine",
            "unit": "box", "reorder_level": 10,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("unit", form.errors)
        self.product.refresh_from_db()
        self.product.unit = "bottle"
        with self.assertRaises(ValidationError):
            self.product.full_clean()

    def test_supplier_create_update_search_delete(self):
        response = self.client.post(reverse("supplier_add"), {
            "name": "New supplier", "email": "supplier@example.com", "is_active": "on",
        })
        supplier = Supplier.objects.get(name="New supplier")
        self.assertRedirects(response, reverse("supplier_detail", args=[supplier.pk]))
        response = self.client.post(reverse("supplier_edit", args=[supplier.pk]), {
            "name": "Edited supplier", "phone": "1234567890", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        supplier.refresh_from_db()
        self.assertEqual(supplier.phone, "1234567890")
        response = self.client.get(reverse("supplier_list"), {"q": "1234567890"})
        self.assertEqual(list(response.context["suppliers"]), [supplier])
        self.client.post(reverse("supplier_delete", args=[supplier.pk]))
        self.assertFalse(Supplier.objects.filter(pk=supplier.pk).exists())

    def test_protected_records_are_not_deleted(self):
        for name, obj in [("product_delete", self.product), ("supplier_delete", self.supplier)]:
            response = self.client.post(reverse(name, args=[obj.pk]), follow=True)
            self.assertContains(response, "cannot be deleted")
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_batch_create_and_adjust_view_validation(self):
        response = self.client.post(reverse("batch_add"), self.batch_data())
        batch = Batch.objects.get(batch_number="B002")
        self.assertRedirects(response, reverse("batch_adjust", args=[batch.pk]))
        self.assertEqual(batch.quantity, 0)
        url = reverse("batch_adjust", args=[batch.pk])
        self.client.post(url, {"change": 8, "reason": "Delivery"})
        response = self.client.post(url, {"change": -9, "reason": "Invalid"})
        self.assertContains(response, "Stock cannot go below zero")
        batch.refresh_from_db()
        self.assertEqual(batch.quantity, 8)
        self.assertEqual(self.client.get(reverse("batch_adjust", args=[99999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("batch_adjust", args=[99999]), {
            "change": 1, "reason": "Missing",
        }).status_code, 404)

    def test_batch_dates_prices_duplicates_and_inactive_choices(self):
        invalid_cases = [
            {"expiry_date": self.today - timedelta(days=1)},
            {"manufacture_date": self.today + timedelta(days=1)},
            {"received_date": self.today + timedelta(days=1)},
            {"purchase_price": "-1.00"}, {"selling_price": "-1.00"},
            {"batch_number": "B001"},
        ]
        for changes in invalid_cases:
            with self.subTest(changes=changes):
                self.assertFalse(BatchForm(data=self.batch_data(**changes)).is_valid())
        Supplier.objects.filter(pk=self.supplier.pk).update(is_active=False)
        self.assertFalse(BatchForm(data=self.batch_data()).is_valid())

    def test_batch_edit_cannot_change_identity_or_quantity(self):
        self.adjust(12)
        other = Product.objects.create(sku="OTHER", name="Other")
        response = self.client.post(reverse("batch_edit", args=[self.batch.pk]), self.batch_data(
            product=other.pk, batch_number="TAMPERED", quantity=999, selling_price="22.00",
        ))
        self.assertEqual(response.status_code, 302)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.product_id, self.product.pk)
        self.assertEqual(self.batch.batch_number, "B001")
        self.assertEqual(self.batch.quantity, 12)
        self.assertEqual(str(self.batch.selling_price), "22.00")

    def test_database_rejects_negative_stock(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Batch.objects.filter(pk=self.batch.pk).update(quantity=-1)

    def test_forms_and_detail_pages_render(self):
        for name, args in [
            ("product_add", []), ("supplier_add", []), ("batch_add", []),
            ("product_edit", [self.product.pk]), ("supplier_edit", [self.supplier.pk]),
            ("batch_edit", [self.batch.pk]), ("supplier_detail", [self.supplier.pk]),
            ("batch_adjust", [self.batch.pk]), ("password_change", []),
            ("product_delete", [self.product.pk]), ("supplier_delete", [self.supplier.pk]),
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)

    def test_pagination_preserves_filters(self):
        Product.objects.bulk_create([
            Product(sku=f"PAGE-{i}", name=f"Paged product {i:02d}") for i in range(22)
        ])
        response = self.client.get(reverse("product_list"), {"q": "Paged", "kind": "medicine"})
        self.assertContains(response, "?q=Paged&amp;kind=medicine&amp;page=2")
        response = self.client.get(reverse("product_list"), {"q": "Paged", "kind": "medicine", "page": 2})
        self.assertEqual(len(response.context["products"]), 2)

    def test_csrf_required_and_get_does_not_delete_or_logout(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("batch_adjust", args=[self.batch.pk]), {
            "change": 1, "reason": "No token",
        }).status_code, 403)
        self.assertEqual(client.get(reverse("product_delete", args=[self.product.pk])).status_code, 200)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertEqual(client.get(reverse("logout")).status_code, 405)

    def test_admin_bootstrap_is_idempotent_and_does_not_reset_password(self):
        with patch.dict("os.environ", {
            "ADMIN_USERNAME": "first-admin", "ADMIN_PASSWORD": "Bootstrap-test-long!925",
        }):
            call_command("bootstrap_admin", stdout=StringIO())
            user = get_user_model().objects.get(username="first-admin")
            original = user.password
            call_command("bootstrap_admin", stdout=StringIO())
            user.refresh_from_db()
            self.assertTrue(user.is_superuser)
            self.assertEqual(user.password, original)

    @patch(
        "inventory.management.commands.seed_demo_data.Command._has_interactive_terminal",
        return_value=True,
    )
    @patch(
        "inventory.management.commands.seed_demo_data.getpass.getpass",
        side_effect=["Demo-seed-password!582", "Demo-seed-password!582"],
    )
    def test_demo_seed_creates_staff_and_inventory_idempotently(self, prompt, is_interactive):
        output = StringIO()
        call_command("seed_demo_data", stdout=output)

        User = get_user_model()
        demo_users = list(User.objects.filter(username__startswith="demo_operator_"))
        self.assertEqual(len(demo_users), 2)
        self.assertTrue(all(user.is_active and user.is_staff for user in demo_users))
        self.assertTrue(all(not user.is_superuser for user in demo_users))
        self.assertTrue(all(user.check_password("Demo-seed-password!582") for user in demo_users))
        self.assertEqual(Product.objects.filter(sku__startswith="DEMO-").count(), 4)
        self.assertEqual(Batch.objects.filter(batch_number__startswith="DEMO-").count(), 4)
        self.assertEqual(
            StockAdjustment.objects.filter(
                batch__batch_number__startswith="DEMO-"
            ).count(),
            4,
        )
        self.assertIn("4 products and 4 batches created", output.getvalue())

        passwords = {user.username: user.password for user in demo_users}
        call_command("seed_demo_data", stdout=StringIO())
        self.assertEqual(Product.objects.filter(sku__startswith="DEMO-").count(), 4)
        self.assertEqual(Batch.objects.filter(batch_number__startswith="DEMO-").count(), 4)
        self.assertEqual(
            StockAdjustment.objects.filter(
                batch__batch_number__startswith="DEMO-"
            ).count(),
            4,
        )
        for user in demo_users:
            user.refresh_from_db()
            self.assertEqual(user.password, passwords[user.username])
        self.assertEqual(prompt.call_count, 2)

    @patch(
        "inventory.management.commands.seed_demo_data.Command._has_interactive_terminal",
        return_value=True,
    )
    @patch(
        "inventory.management.commands.seed_demo_data.getpass.getpass",
        side_effect=["Demo-seed-password!582", "Not-the-same-password!582"],
    )
    def test_demo_seed_rejects_mismatched_password_before_creating_records(
        self, prompt, is_interactive
    ):
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, "passwords did not match"):
            call_command("seed_demo_data", stdout=StringIO())
        self.assertFalse(
            get_user_model().objects.filter(username__startswith="demo_operator_").exists()
        )
        self.assertFalse(Product.objects.filter(sku__startswith="DEMO-").exists())

    @patch(
        "inventory.management.commands.seed_demo_data.Command._has_interactive_terminal",
        return_value=False,
    )
    def test_demo_seed_requires_a_terminal_before_creating_records(self, is_interactive):
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, "A terminal is required"):
            call_command("seed_demo_data", stdout=StringIO())
        self.assertFalse(
            get_user_model().objects.filter(username__startswith="demo_operator_").exists()
        )
        self.assertFalse(Product.objects.filter(sku__startswith="DEMO-").exists())

    @patch(
        "inventory.management.commands.seed_demo_data.getpass.getpass",
        side_effect=AssertionError("Deployment seeding must not prompt."),
    )
    def test_demo_seed_can_run_noninteractively_with_environment_password(self, prompt):
        with patch.dict("os.environ", {
            "SEED_DEMO_DATA": "true",
            "DEMO_PASSWORD": "Deployment-demo-password!682",
        }):
            output = StringIO()
            call_command(
                "seed_demo_data",
                enable_if_env="SEED_DEMO_DATA",
                password_env="DEMO_PASSWORD",
                stdout=output,
            )

        User = get_user_model()
        demo_users = list(User.objects.filter(username__startswith="demo_operator_"))
        self.assertEqual(len(demo_users), 2)
        self.assertTrue(all(
            user.check_password("Deployment-demo-password!682") for user in demo_users
        ))
        self.assertEqual(Product.objects.filter(sku__startswith="DEMO-").count(), 4)
        self.assertIn("4 products and 4 batches created", output.getvalue())

    @patch(
        "inventory.management.commands.seed_demo_data.getpass.getpass",
        side_effect=AssertionError("Disabled deployment seeding must not prompt."),
    )
    def test_demo_seed_is_disabled_without_deployment_opt_in(self, prompt):
        with patch.dict("os.environ", {"SEED_DEMO_DATA": "", "DEMO_PASSWORD": ""}):
            output = StringIO()
            call_command(
                "seed_demo_data",
                enable_if_env="SEED_DEMO_DATA",
                password_env="DEMO_PASSWORD",
                stdout=output,
            )

        self.assertIn("Demo seeding skipped", output.getvalue())
        self.assertFalse(
            get_user_model().objects.filter(username__startswith="demo_operator_").exists()
        )
        self.assertFalse(Product.objects.filter(sku__startswith="DEMO-").exists())
