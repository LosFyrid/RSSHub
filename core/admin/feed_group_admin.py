from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import core_admin_site
from core.forms import FeedGroupForm
from core.models import FeedGroup


class FeedGroupAdmin(admin.ModelAdmin):
    form = FeedGroupForm
    list_display = ("name", "workspace", "slug", "feed_count", "show_exports")
    search_fields = ("name", "slug", "workspace__name", "description")
    list_filter = ("workspace",)
    fields = ("workspace", "name", "description", "slug", "show_exports")
    readonly_fields = ("slug", "show_exports")

    @admin.display(description=_("Feeds"))
    def feed_count(self, obj):
        return obj.feeds.count()

    @admin.display(description=_("Exports"))
    def show_exports(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            "<a href='{0}' target='_blank'>translated RSS</a> | "
            "<a href='{1}' target='_blank'>proxy RSS</a> | "
            "<a href='{2}' target='_blank'>translated OPML</a> | "
            "<a href='{3}' target='_blank'>proxy OPML</a>",
            f"/rss/group/{obj.workspace.slug}/{obj.slug}",
            f"/rss/group/{obj.workspace.slug}/{obj.slug}/proxy",
            f"/rss/group/{obj.workspace.slug}/{obj.slug}/opml",
            f"/rss/group/{obj.workspace.slug}/{obj.slug}/proxy/opml",
        )


core_admin_site.register(FeedGroup, FeedGroupAdmin)
