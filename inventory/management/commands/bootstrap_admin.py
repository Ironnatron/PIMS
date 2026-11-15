import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the first administrator from temporary environment variables; never reset an existing account."

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "")
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username and not password:
            self.stdout.write("Administrator bootstrap not requested.")
            return
        if not username or not password:
            raise CommandError("Both ADMIN_USERNAME and ADMIN_PASSWORD must be set.")
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write("Account already exists; no changes made.")
            return
        user = User(username=username, is_staff=True, is_superuser=True)
        validate_password(password, user=user)
        user.set_password(password)
        user.full_clean()
        user.save()
        self.stdout.write(self.style.SUCCESS("Administrator created. Remove ADMIN_PASSWORD from the deployment environment."))
