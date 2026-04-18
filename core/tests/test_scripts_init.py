from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from scripts.init import create_superuser


@override_settings(
    DEFAULT_SUPERUSER_USERNAME="admin",
    DEFAULT_SUPERUSER_EMAIL="admin@example.com",
    DEFAULT_SUPERUSER_PASSWORD="secret-pass",
)
class CreateSuperuserTests(TestCase):
    def test_create_superuser_creates_missing_default_user(self):
        output = StringIO()
        with patch("sys.stdout", output):
            create_superuser()

        User = get_user_model()
        admin = User.objects.get(username="admin")

        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertIn("Successfully created a new superuser", output.getvalue())

    def test_create_superuser_is_idempotent_when_superuser_exists(self):
        User = get_user_model()
        User.objects.create_superuser("admin", "admin@example.com", "secret-pass")

        output = StringIO()
        with patch("sys.stdout", output):
            create_superuser()

        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        self.assertIn("Superuser already exists", output.getvalue())

    def test_create_superuser_skips_existing_non_superuser_username(self):
        User = get_user_model()
        User.objects.create_user("admin", "member@example.com", "secret-pass")

        output = StringIO()
        with patch("sys.stdout", output):
            create_superuser()

        existing = User.objects.get(username="admin")
        self.assertFalse(existing.is_superuser)
        self.assertEqual(User.objects.filter(username="admin").count(), 1)
        self.assertIn(
            "skipping automatic superuser creation",
            output.getvalue(),
        )
