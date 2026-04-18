from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkspaceMembership(models.Model):
    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"
    ROLE_CHOICES = [
        (OWNER, _("Owner")),
        (MANAGER, _("Manager")),
        (VIEWER, _("Viewer")),
    ]
    MANAGE_ROLES = {OWNER, MANAGER}

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
        verbose_name=_("User"),
    )
    workspace = models.ForeignKey(
        "Workspace",
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("Workspace"),
    )
    role = models.CharField(
        max_length=32,
        choices=ROLE_CHOICES,
        default=VIEWER,
        verbose_name=_("Role"),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Workspace Membership")
        verbose_name_plural = _("Workspace Memberships")
        ordering = ["workspace__name", "user__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "workspace"],
                name="unique_user_workspace_membership",
            )
        ]

    def __str__(self):
        return f"{self.workspace.name} / {self.user.username}"

    def can_manage(self):
        return self.is_active and self.role in self.MANAGE_ROLES
