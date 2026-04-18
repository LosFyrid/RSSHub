from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0040_alter_feed_source_kind_alter_feed_workspace_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkspaceInvitation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, verbose_name="Email")),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Owner"), ("manager", "Manager"), ("viewer", "Viewer")],
                        default="viewer",
                        max_length=32,
                        verbose_name="Role",
                    ),
                ),
                ("note", models.TextField(blank=True, default="", verbose_name="Note")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted", "Accepted"),
                            ("declined", "Declined"),
                            ("canceled", "Canceled"),
                        ],
                        default="pending",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                ("responded_at", models.DateTimeField(blank=True, null=True, verbose_name="Responded At")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                (
                    "invited_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sent_workspace_invitations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Invited By",
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workspace_invitations",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Target User",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invitations",
                        to="core.workspace",
                        verbose_name="Workspace",
                    ),
                ),
            ],
            options={
                "verbose_name": "Workspace Invitation",
                "verbose_name_plural": "Workspace Invitations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="workspaceinvitation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "pending")),
                fields=("workspace", "email"),
                name="unique_pending_workspace_invitation",
            ),
        ),
    ]
