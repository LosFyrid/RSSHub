from django.urls import path

from . import views

app_name = "hub"

urlpatterns = [
    path("login/", views.hub_login, name="login"),
    path("register/", views.hub_register, name="register"),
    path("logout/", views.hub_logout, name="logout"),
    path("", views.hub_dashboard, name="dashboard"),
    path("console/", views.hub_console, name="console"),
    path("workspaces/create/", views.hub_create_workspace, name="create_workspace"),
    path("workspaces/update/", views.hub_update_workspace, name="update_workspace"),
    path("providers/create/", views.hub_create_provider, name="create_provider"),
    path("preferences/", views.hub_set_preferences, name="set_preferences"),
    path("account/password/", views.hub_change_password, name="change_password"),
    path("feeds/create/", views.hub_create_feed, name="create_feed"),
    path("feeds/<int:feed_id>/update/", views.hub_update_feed, name="update_feed"),
    path("feeds/<int:feed_id>/refresh/", views.hub_refresh_feed, name="refresh_feed"),
    path("feeds/import-opml/", views.hub_import_opml, name="import_opml"),
    path("feeds/bulk-export/", views.hub_bulk_export, name="bulk_export"),
    path("feeds/bulk-edit/", views.hub_bulk_edit, name="bulk_edit"),
    path(
        "workspaces/providers/",
        views.hub_update_workspace_providers,
        name="update_workspace_providers",
    ),
    path(
        "workspaces/members/invite/",
        views.hub_invite_workspace_member,
        name="invite_workspace_member",
    ),
    path(
        "workspaces/members/<int:membership_id>/role/",
        views.hub_update_workspace_member,
        name="update_workspace_member",
    ),
    path(
        "workspaces/members/<int:membership_id>/remove/",
        views.hub_remove_workspace_member,
        name="remove_workspace_member",
    ),
    path(
        "inbox/invitations/<int:invitation_id>/respond/",
        views.hub_respond_invitation,
        name="respond_invitation",
    ),
]
