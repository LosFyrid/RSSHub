from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from autoslug import AutoSlugField


class Workspace(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))
    slug = AutoSlugField(
        verbose_name=_("URL Slug"),
        populate_from="name",
        unique=True,
    )
    description = models.TextField(blank=True, default="", verbose_name=_("Description"))
    default_target_language = models.CharField(
        max_length=50,
        default="Chinese Simplified",
        verbose_name=_("Default Target Language"),
    )
    default_translator_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="workspace_default_translator",
        verbose_name=_("Default Translator Type"),
    )
    default_translator_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        verbose_name=_("Default Translator ID"),
    )
    default_translator = GenericForeignKey(
        "default_translator_content_type", "default_translator_object_id"
    )
    default_summarizer = models.ForeignKey(
        "OpenAIAgent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="workspaces_as_default_summarizer",
        verbose_name=_("Default Summarizer"),
    )
    is_default = models.BooleanField(default=False, verbose_name=_("Default Workspace"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated At"))

    class Meta:
        verbose_name = _("Workspace")
        verbose_name_plural = _("Workspaces")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.default_translator_content_type_id:
            self.default_translator_content_type_id = None
            self.default_translator_object_id = None
        super().save(*args, **kwargs)
        if self.is_default:
            Workspace.objects.exclude(pk=self.pk).filter(is_default=True).update(
                is_default=False
            )

    def get_default_translator(self):
        return self.default_translator

    def get_default_summarizer(self):
        return self.default_summarizer

    @classmethod
    def get_default(cls):
        workspace, created = cls.objects.get_or_create(
            slug="default-workspace",
            defaults={
                "name": "Default Workspace",
                "description": "Auto-created default workspace",
                "is_default": True,
            },
        )
        if not workspace.is_default:
            workspace.is_default = True
            workspace.save(update_fields=["is_default"])
        return workspace


def get_default_workspace_id():
    return Workspace.get_default().pk
