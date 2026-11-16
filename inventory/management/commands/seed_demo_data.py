import getpass
import os
import sys
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from inventory.models import Batch, Product, Supplier
from inventory.services import adjust_stock


class Command(BaseCommand):
    help = "Create labeled demo users and inventory without changing existing records."

    account_specs = [
        {
            "username": "demo_operator_1",
            "first_name": "Demo",
            "last_name": "Operator One",
            "email": "demo.operator1@example.invalid",
        },
        {
            "username": "demo_operator_2",
            "first_name": "Demo",
            "last_name": "Operator Two",
            "email": "demo.operator2@example.invalid",
        },
    ]

    supplier_specs = [
        {
            "name": "Demo Northstar Pharma",
            "defaults": {
                "email": "northstar@example.invalid",
                "tax_id": "DEMO-TAX-001",
                "license_number": "DEMO-LIC-001",
            },
        },
        {
            "name": "Demo Harbor Medical Supply",
            "defaults": {
                "email": "harbor@example.invalid",
                "tax_id": "DEMO-TAX-002",
                "license_number": "DEMO-LIC-002",
            },
        },
    ]

    product_specs = [
        {
            "sku": "DEMO-PARA-500",
            "defaults": {
                "name": "Paracetamol 500 mg Tablets",
                "kind": Product.Kind.MEDICINE,
                "generic_name": "Paracetamol",
                "manufacturer": "Demo Therapeutics",
                "strength": "500 mg",
                "dosage_form": "Tablet",
                "unit": "strip",
                "reorder_level": 20,
            },
            "supplier": "Demo Northstar Pharma",
            "batch_number": "DEMO-PARA-01",
            "received_days_ago": 20,
            "expiry_days_from_today": 240,
            "quantity": 16,
            "purchase_price": "10.00",
            "selling_price": "14.00",
        },
        {
            "sku": "DEMO-AMOX-250",
            "defaults": {
                "name": "Amoxicillin 250 mg Capsules",
                "kind": Product.Kind.MEDICINE,
                "generic_name": "Amoxicillin",
                "manufacturer": "Demo Therapeutics",
                "strength": "250 mg",
                "dosage_form": "Capsule",
                "unit": "box",
                "requires_prescription": True,
                "reorder_level": 10,
            },
            "supplier": "Demo Northstar Pharma",
            "batch_number": "DEMO-AMOX-01",
            "received_days_ago": 15,
            "expiry_days_from_today": 45,
            "quantity": 42,
            "purchase_price": "35.00",
            "selling_price": "48.00",
        },
        {
            "sku": "DEMO-VITC-500",
            "defaults": {
                "name": "Vitamin C 500 mg Tablets",
                "kind": Product.Kind.MEDICINE,
                "generic_name": "Vitamin C",
                "manufacturer": "Demo Wellness",
                "strength": "500 mg",
                "dosage_form": "Tablet",
                "unit": "bottle",
                "reorder_level": 15,
            },
            "supplier": "Demo Harbor Medical Supply",
            "batch_number": "DEMO-VITC-01",
            "received_days_ago": 30,
            "expiry_days_from_today": 180,
            "quantity": 48,
            "purchase_price": "22.00",
            "selling_price": "30.00",
        },
        {
            "sku": "DEMO-GLOVES-M",
            "defaults": {
                "name": "Nitrile Examination Gloves - Medium",
                "kind": Product.Kind.OTHER,
                "manufacturer": "Demo Medical Goods",
                "dosage_form": "",
                "unit": "box",
                "reorder_level": 10,
            },
            "supplier": "Demo Harbor Medical Supply",
            "batch_number": "DEMO-GLOVES-01",
            "received_days_ago": 10,
            "expiry_days_from_today": 365,
            "quantity": 7,
            "purchase_price": "90.00",
            "selling_price": "120.00",
        },
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--enable-if-env",
            metavar="NAME",
            help="Run only when the named environment variable is set to true.",
        )
        parser.add_argument(
            "--password-env",
            metavar="NAME",
            help="Read a new demo account password from the named environment variable.",
        )

    def handle(self, *args, **options):
        enable_env = options.get("enable_if_env")
        if enable_env and os.environ.get(enable_env, "").lower() not in {
            "1", "true", "yes", "on",
        }:
            self.stdout.write("Demo seeding skipped; the opt-in environment flag is not enabled.")
            return

        User = get_user_model()
        existing_users = {
            user.username: user
            for user in User.objects.filter(
                username__in=[spec["username"] for spec in self.account_specs]
            )
        }
        missing_specs = [
            spec for spec in self.account_specs if spec["username"] not in existing_users
        ]

        for username, user in existing_users.items():
            if not user.is_active or not user.is_staff or user.is_superuser:
                raise CommandError(
                    f"Existing account {username!r} is not an active, non-superuser "
                    "staff account. It was not changed; resolve the username conflict first."
                )

        password = None
        if missing_specs:
            password_env = options.get("password_env")
            if password_env:
                password = os.environ.get(password_env, "")
                if not password:
                    raise CommandError(
                        f"Set {password_env} to a password before enabling demo seeding."
                    )
                self._validate_password(User, missing_specs, password)
            else:
                password = self._prompt_password(User, missing_specs)

        created = {"users": 0, "suppliers": 0, "products": 0, "batches": 0}
        with transaction.atomic():
            for spec in missing_specs:
                User.objects.create_user(
                    username=spec["username"],
                    password=password,
                    first_name=spec["first_name"],
                    last_name=spec["last_name"],
                    email=spec["email"],
                    is_active=True,
                    is_staff=True,
                    is_superuser=False,
                )
                created["users"] += 1

            actor = User.objects.get(username=self.account_specs[0]["username"])
            suppliers = {}
            for spec in self.supplier_specs:
                supplier, was_created = Supplier.objects.get_or_create(
                    name=spec["name"], defaults=spec["defaults"],
                )
                if not supplier.is_active:
                    raise CommandError(
                        f"Demo supplier {supplier.name!r} already exists but is inactive; "
                        "it was not changed."
                    )
                suppliers[spec["name"]] = supplier
                created["suppliers"] += int(was_created)

            today = timezone.localdate()
            for spec in self.product_specs:
                product, was_created = Product.objects.get_or_create(
                    sku=spec["sku"], defaults=spec["defaults"],
                )
                if not product.is_active:
                    raise CommandError(
                        f"Demo product {product.sku!r} already exists but is inactive; "
                        "it was not changed."
                    )
                created["products"] += int(was_created)

                batch, was_created = Batch.objects.get_or_create(
                    product=product,
                    batch_number=spec["batch_number"],
                    defaults={
                        "supplier": suppliers[spec["supplier"]],
                        "received_date": today - timedelta(days=spec["received_days_ago"]),
                        "manufacture_date": today - timedelta(
                            days=spec["received_days_ago"] + 120
                        ),
                        "expiry_date": today + timedelta(
                            days=spec["expiry_days_from_today"]
                        ),
                        "purchase_price": spec["purchase_price"],
                        "selling_price": spec["selling_price"],
                    },
                )
                created["batches"] += int(was_created)
                if was_created:
                    adjust_stock(
                        batch_id=batch.pk,
                        change=spec["quantity"],
                        reason="Demo data: initial stock receipt",
                        user=actor,
                    )

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready: "
            f"{created['users']} users, {created['suppliers']} suppliers, "
            f"{created['products']} products and {created['batches']} batches created."
        ))
        self.stdout.write(
            "Existing demo accounts and inventory records were left unchanged."
        )
        if missing_specs:
            self.stdout.write(
                "The newly created demo accounts share the supplied password. "
                "Both are active staff accounts with full inventory access, not admin access."
            )
        else:
            self.stdout.write("No account passwords were changed.")

    def _prompt_password(self, User, missing_specs):
        if not self._has_interactive_terminal():
            raise CommandError(
                "A terminal is required to set demo passwords. Run this command "
                "interactively; no records were created."
            )
        try:
            password = getpass.getpass(
                "Choose a password for the new demo account(s): "
            )
            confirmation = getpass.getpass("Confirm the demo password: ")
        except EOFError as error:
            raise CommandError(
                "A terminal is required to set demo passwords. Run this command "
                "interactively; no records were created."
            ) from error

        if not password:
            raise CommandError("The demo password cannot be blank.")
        if password != confirmation:
            raise CommandError("The passwords did not match; no records were created.")

        return self._validate_password(User, missing_specs, password)

    def _validate_password(self, User, missing_specs, password):
        errors = []
        for spec in missing_specs:
            candidate = User(
                username=spec["username"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                email=spec["email"],
            )
            try:
                validate_password(password, user=candidate)
            except ValidationError as error:
                errors.extend(error.messages)
        if errors:
            raise CommandError(
                "The password does not meet the configured requirements: "
                + " ".join(dict.fromkeys(errors))
            )
        return password

    def _has_interactive_terminal(self):
        return sys.stdin.isatty()
