from django.db import models
from django.utils.translation import gettext_lazy as _
from autoslug import AutoSlugField


class FeedGroup(models.Model):
    workspace = models.ForeignKey(
        "Workspace",
        on_delete=models.CASCADE,
        related_name="groups",
        verbose_name=_("Workspace"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    slug = AutoSlugField(
        verbose_name=_("URL Slug"),
        populate_from="name",
        unique_with="workspace",
    )
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Feed Group")
        verbose_name_plural = _("Feed Groups")
        ordering = ["workspace__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"], name="unique_workspace_group_name"
            )
        ]

    def __str__(self):
        return f"{self.workspace.name} / {self.name}"
