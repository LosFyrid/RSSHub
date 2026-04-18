from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class WorkspaceInvitation(models.Model):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELED = "canceled"
    STATUS_CHOICES = [
        (PENDING, _("Pending")),
        (ACCEPTED, _("Accepted")),
        (DECLINED, _("Declined")),
        (CANCELED, _("Canceled")),
    ]

    workspace = models.ForeignKey(
        "Workspace",
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name=_("Workspace"),
    )
    email = models.EmailField(verbose_name=_("Email"))
    role = models.CharField(
        max_length=32,
        choices=[
            ("owner", _("Owner")),
            ("manager", _("Manager")),
            ("viewer", _("Viewer")),
        ],
        default="viewer",
        verbose_name=_("Role"),
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_workspace_invitations",
        verbose_name=_("Invited By"),
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workspace_invitations",
        verbose_name=_("Target User"),
    )
    note = models.TextField(blank=True, default="", verbose_name=_("Note"))
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=PENDING,
        verbose_name=_("Status"),
    )
    responded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Responded At"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Workspace Invitation")
        verbose_name_plural = _("Workspace Invitations")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "email"],
                condition=models.Q(status="pending"),
                name="unique_pending_workspace_invitation",
            )
        ]

    def __str__(self):
        return f"{self.workspace.name} -> {self.email}"

    def bind_target_user(self):
        if self.target_user_id or not self.email:
            return
        user_model = self._meta.get_field("target_user").remote_field.model
        matched_user = (
            user_model.objects.filter(email__iexact=self.email).order_by("id").first()
        )
        if matched_user:
            self.target_user = matched_user

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.bind_target_user()
        super().save(*args, **kwargs)

    def accept(self):
        self.status = self.ACCEPTED
        self.responded_at = timezone.now()

    def decline(self):
        self.status = self.DECLINED
        self.responded_at = timezone.now()

    def cancel(self):
        self.status = self.CANCELED
        self.responded_at = timezone.now()
