from datetime import timedelta

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Batch, Product, StockAdjustment, Supplier

User = get_user_model()


class AdministrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="administrator", password="Strong-test-password-902!",
        )
        cls.staff = User.objects.create_user(
            username="staff", password="Strong-staff-password-902!", is_staff=True,
        )
        cls.nonstaff = User.objects.create_user(username="visitor", password="visitor-password-902!")
        cls.group = Group.objects.create(name="Auditors")
        cls.permission = Permission.objects.get(content_type__app_label="inventory", codename="view_product")

    def setUp(self):
        self.client.force_login(self.admin)

    def user_data(self, user, **changes):
        data = {
            "username": user.username, "first_name": user.first_name, "last_name": user.last_name,
            "email": user.email, "is_active": user.is_active, "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "groups": list(user.groups.values_list("pk", flat=True)),
            "user_permissions": list(user.user_permissions.values_list("pk", flat=True)),
        }
        data.update(changes)
        return data

    def test_only_active_staff_superusers_access_every_admin_route(self):
        paths = [
            ("administration_users", []), ("administration_user_add", []),
            ("administration_user_edit", [self.staff.pk]),
            ("administration_user_password", [self.staff.pk]),
            ("administration_user_delete", [self.staff.pk]),
            ("administration_groups", []), ("administration_group_add", []),
            ("administration_group_edit", [self.group.pk]),
            ("administration_group_delete", [self.group.pk]),
        ]
        for name, args in paths:
            url = reverse(name, args=args)
            with self.subTest(path=name):
                self.client.logout()
                self.assertEqual(self.client.get(url).status_code, 302)
                for user in [self.staff, self.nonstaff]:
                    self.client.force_login(user)
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {}).status_code, 403)
                self.client.force_login(self.admin)
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_account_creation_and_edit_preserve_roles_permissions_and_log(self):
        url = reverse("administration_user_add")
        response = self.client.post(url, {
            "username": "new-staff", "first_name": "New", "email": "new@example.com",
            "is_active": "on", "is_staff": "on", "groups": [self.group.pk],
            "user_permissions": [self.permission.pk],
            "password1": "Strong-new-password-736!", "password2": "Strong-new-password-736!",
        })
        self.assertRedirects(response, reverse("administration_users"))
        user = User.objects.get(username="new-staff")
        self.assertTrue(user.check_password("Strong-new-password-736!"))
        self.assertEqual(list(user.groups.all()), [self.group])
        self.assertEqual(list(user.user_permissions.all()), [self.permission])
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(user.pk), action_flag=ADDITION).exists())

        edit = reverse("administration_user_edit", args=[user.pk])
        page = self.client.get(edit)
        self.assertContains(page, f'<option value="{self.group.pk}" selected>')
        self.assertContains(page, f'<option value="{self.permission.pk}" selected>')
        response = self.client.post(edit, self.user_data(user, first_name="Updated", groups=[], user_permissions=[]))
        self.assertRedirects(response, reverse("administration_users"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated")
        self.assertFalse(user.groups.exists())
        self.assertFalse(user.user_permissions.exists())
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(user.pk), action_flag=CHANGE).exists())

    def test_creation_rejects_weak_password_and_unstaffed_superuser(self):
        response = self.client.post(reverse("administration_user_add"), {
            "username": "new-admin", "is_active": "on", "is_superuser": "on",
            "password1": "123", "password2": "123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A superuser must have staff access")
        self.assertFalse(User.objects.filter(username="new-admin").exists())

    def test_self_deactivation_demotion_and_deletion_are_rejected(self):
        for field in ["is_active", "is_staff", "is_superuser"]:
            response = self.client.post(
                reverse("administration_user_edit", args=[self.admin.pk]),
                self.user_data(self.admin, **{field: False}),
            )
            self.assertEqual(response.status_code, 200)
            self.admin.refresh_from_db()
            self.assertTrue(getattr(self.admin, field))
        response = self.client.post(reverse("administration_user_delete", args=[self.admin.pk]), follow=True)
        self.assertContains(response, "cannot delete your own account")
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_admin_can_deactivate_another_admin_when_an_admin_remains(self):
        other = User.objects.create_superuser(username="other", password="Strong-other-password-902!")
        response = self.client.post(
            reverse("administration_user_edit", args=[other.pk]),
            self.user_data(other, is_active=False),
        )
        self.assertRedirects(response, reverse("administration_users"))
        other.refresh_from_db()
        self.assertFalse(other.is_active)

    def test_password_reset_validates_and_invalidates_other_sessions(self):
        second_client = Client()
        self.assertTrue(second_client.login(username="staff", password="Strong-staff-password-902!"))
        url = reverse("administration_user_password", args=[self.staff.pk])
        response = self.client.post(url, {"new_password1": "123", "new_password2": "123"})
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("Strong-staff-password-902!"))
        response = self.client.post(url, {
            "new_password1": "Fresh-staff-password-465!", "new_password2": "Fresh-staff-password-465!",
        })
        self.assertRedirects(response, reverse("administration_users"))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("Fresh-staff-password-465!"))
        self.assertEqual(second_client.get(reverse("dashboard")).status_code, 302)
        entry = LogEntry.objects.filter(object_id=str(self.staff.pk), action_flag=CHANGE).latest("pk")
        self.assertNotIn("Fresh-staff-password-465!", entry.change_message)

    def test_resetting_own_password_keeps_current_session(self):
        response = self.client.post(reverse("administration_user_password", args=[self.admin.pk]), {
            "new_password1": "Fresh-admin-password-465!", "new_password2": "Fresh-admin-password-465!",
        })
        self.assertRedirects(response, reverse("administration_users"))
        self.assertEqual(self.client.get(reverse("administration_users")).status_code, 200)

    def test_group_management_and_direct_permissions_do_not_change_inventory_access(self):
        response = self.client.post(reverse("administration_group_add"), {
            "name": "Managers", "permissions": [self.permission.pk],
        })
        self.assertRedirects(response, reverse("administration_groups"))
        group = Group.objects.get(name="Managers")
        self.assertEqual(list(group.permissions.all()), [self.permission])
        self.staff.groups.add(group)
        response = self.client.post(reverse("administration_group_edit", args=[group.pk]), {
            "name": "Managers renamed", "permissions": [],
        })
        self.assertRedirects(response, reverse("administration_groups"))
        group.refresh_from_db()
        self.assertFalse(group.permissions.exists())
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("product_list")).status_code, 200)
        self.client.force_login(self.admin)
        group_id = group.pk
        response = self.client.post(reverse("administration_group_delete", args=[group_id]))
        self.assertRedirects(response, reverse("administration_groups"))
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())
        self.assertFalse(self.staff.groups.filter(pk=group_id).exists())
        self.assertTrue(LogEntry.objects.filter(object_id=str(group_id), action_flag=DELETION).exists())

    def test_user_with_stock_history_cannot_be_deleted(self):
        today = timezone.localdate()
        product = Product.objects.create(sku="A", name="Product")
        supplier = Supplier.objects.create(name="Supplier")
        batch = Batch.objects.create(
            product=product, supplier=supplier, batch_number="1", received_date=today,
            expiry_date=today + timedelta(days=1), purchase_price=1, selling_price=1,
        )
        StockAdjustment.objects.create(
            batch=batch, change=1, resulting_quantity=1, reason="Receipt", user=self.staff,
        )
        response = self.client.post(reverse("administration_user_delete", args=[self.staff.pk]), follow=True)
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())
        self.assertFalse(LogEntry.objects.filter(
            object_id=str(self.staff.pk), content_type__model="user", action_flag=DELETION,
        ).exists())

    def test_admin_actions_require_csrf_and_delete_requires_post(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        url = reverse("administration_group_delete", args=[self.group.pk])
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())
