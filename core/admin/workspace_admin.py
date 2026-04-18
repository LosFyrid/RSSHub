from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import core_admin_site
from core.forms import WorkspaceForm
from core.models import Workspace


class WorkspaceAdmin(admin.ModelAdmin):
    form = WorkspaceForm
    list_display = (
        "name",
        "slug",
        "default_target_language",
        "is_default",
        "is_active",
        "show_exports",
    )
    search_fields = ("name", "slug", "description")
    list_filter = ("is_default", "is_active", "default_target_language")
    fields = (
        "name",
        "description",
        "default_target_language",
        "is_default",
        "is_active",
        "slug",
        "show_exports",
    )
    readonly_fields = ("slug", "show_exports")

    @admin.display(description=_("Exports"))
    def show_exports(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            "<a href='{0}' target='_blank'>translated RSS</a> | "
            "<a href='{1}' target='_blank'>proxy RSS</a> | "
            "<a href='{2}' target='_blank'>translated OPML</a> | "
            "<a href='{3}' target='_blank'>proxy OPML</a>",
            f"/rss/workspace/{obj.slug}",
            f"/rss/workspace/{obj.slug}/proxy",
            f"/rss/workspace/{obj.slug}/opml",
            f"/rss/workspace/{obj.slug}/proxy/opml",
        )


core_admin_site.register(Workspace, WorkspaceAdmin)
