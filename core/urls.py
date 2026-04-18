from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.hub_dashboard, name="hub_dashboard"),
    path("feeds/create/", views.hub_create_feed, name="hub_create_feed"),
    path("feeds/import-opml/", views.hub_import_opml, name="hub_import_opml"),
    path("feeds/bulk-export/", views.hub_bulk_export, name="hub_bulk_export"),
    # path("filter/<str:name>", views.filter, name="filter"),
    path(
        "tag/proxy/<str:tag>",
        views.tag,
        kwargs={"feed_type": "o", "format": "xml"},
    ),
    path(
        "tag/proxy/<str:tag>/",
        views.tag,
        kwargs={"feed_type": "o", "format": "xml"},
    ),
    path(
        "tag/json/<str:tag>",
        views.tag,
        kwargs={"feed_type": "t", "format": "json"},
    ),
    path(
        "tag/json/<str:tag>/",
        views.tag,
        kwargs={"feed_type": "t", "format": "json"},
    ),
    path(
        "tag/<str:tag>",
        views.tag,
        kwargs={"feed_type": "t", "format": "xml"},
    ),
    path(
        "tag/<str:tag>/",
        views.tag,
        kwargs={"feed_type": "t", "format": "xml"},
    ),
    path(
        "proxy/<str:feed_slug>", views.rss, kwargs={"feed_type": "o", "format": "xml"}
    ),
    path(
        "proxy/<str:feed_slug>/", views.rss, kwargs={"feed_type": "o", "format": "xml"}
    ),
    path(
        "json/<str:feed_slug>", views.rss, kwargs={"feed_type": "t", "format": "json"}
    ),
    path(
        "json/<str:feed_slug>/", views.rss, kwargs={"feed_type": "t", "format": "json"}
    ),
    path(
        "workspace/<str:workspace_slug>/proxy",
        views.workspace_feed,
        kwargs={"feed_type": "o", "format": "xml"},
    ),
    path(
        "workspace/<str:workspace_slug>/proxy/",
        views.workspace_feed,
        kwargs={"feed_type": "o", "format": "xml"},
    ),
    path(
        "workspace/<str:workspace_slug>",
        views.workspace_feed,
        kwargs={"feed_type": "t", "format": "xml"},
    ),
    path(
        "workspace/<str:workspace_slug>/",
        views.workspace_feed,
        kwargs={"feed_type": "t", "format": "xml"},
    ),
    path(
        "workspace/<str:workspace_slug>/opml",
        views.workspace_opml,
        kwargs={"variant": "translated"},
        name="workspace_opml",
    ),
    path(
        "workspace/<str:workspace_slug>/opml/",
        views.workspace_opml,
        kwargs={"variant": "translated"},
        name="workspace_opml",
    ),
    path(
        "workspace/<str:workspace_slug>/proxy/opml",
        views.workspace_opml,
        kwargs={"variant": "proxy"},
        name="workspace_proxy_opml",
    ),
    path(
        "workspace/<str:workspace_slug>/proxy/opml/",
        views.workspace_opml,
        kwargs={"variant": "proxy"},
        name="workspace_proxy_opml",
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/proxy",
        views.group_feed,
        kwargs={"feed_type": "o", "format": "xml"},
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/proxy/",
        views.group_feed,
        kwargs={"feed_type": "o", "format": "xml"},
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>",
        views.group_feed,
        kwargs={"feed_type": "t", "format": "xml"},
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/",
        views.group_feed,
        kwargs={"feed_type": "t", "format": "xml"},
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/opml",
        views.group_opml,
        kwargs={"variant": "translated"},
        name="group_opml",
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/opml/",
        views.group_opml,
        kwargs={"variant": "translated"},
        name="group_opml",
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/proxy/opml",
        views.group_opml,
        kwargs={"variant": "proxy"},
        name="group_proxy_opml",
    ),
    path(
        "group/<str:workspace_slug>/<str:group_slug>/proxy/opml/",
        views.group_opml,
        kwargs={"variant": "proxy"},
        name="group_proxy_opml",
    ),
    path("import_opml/", views.import_opml, name="import_opml"),
    # Digest URLs
    path("digest/view/<str:slug>", views.digest_view, name="digest_view"),
    path("digest/view/<str:slug>/", views.digest_view, name="digest_view"),
    path(
        "digest/json/<str:slug>",
        views.digest,
        kwargs={"format": "json"},
        name="digest_json",
    ),
    path(
        "digest/json/<str:slug>/",
        views.digest,
        kwargs={"format": "json"},
        name="digest_json",
    ),
    path(
        "digest/<str:slug>", views.digest, kwargs={"format": "xml"}, name="digest_rss"
    ),
    path(
        "digest/<str:slug>/", views.digest, kwargs={"format": "xml"}, name="digest_rss"
    ),
    path("<str:feed_slug>", views.rss, kwargs={"feed_type": "t", "format": "xml"}),
    path("<str:feed_slug>/", views.rss, kwargs={"feed_type": "t", "format": "xml"}),
]
