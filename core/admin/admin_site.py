from django.contrib.auth.models import User, Group
from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.urls import path, reverse
from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme
from core.models.agent import OpenAIAgent, DeepLAgent, LibreTranslateAgent, TestAgent
from utils.modelAdmin_utils import (
    status_icon,
)
from django.shortcuts import redirect, render

from core.models import Feed, Filter, Tag, Digest, Workspace, FeedGroup


class CoreAdminSite(AdminSite):
    site_header = _("RSSBox Admin")
    site_title = _("RSSBox")
    index_title = _("Dashboard")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("agent/add", agent_add, name="agent_add"),
            path("agent/list", agent_list, name="agent_list"),
        ]
        return custom_urls + urls

    def get_app_list(self, request, app_label=None):
        def admin_url(name, *args):
            return reverse(name, args=args)

        # app_list = super().get_app_list(request, app_label)
        app_list = [
            {
                "name": "",
                "app_label": "core",
                "app_url": "/admin/core/",
                "has_module_perms": True,
                "models": [
                    {
                        "model": Feed,
                        "name": "Feeds",
                        "object_name": "Feed",
                        "perms": {
                            "add": True,
                            "change": True,
                            "delete": True,
                            "view": True,
                        },
                        "admin_url": admin_url("admin:core_feed_changelist"),
                        "add_url": admin_url("admin:core_feed_add"),
                        "view_only": False,
                    },
                    {
                        "model": Workspace,
                        "name": "Workspaces",
                        "object_name": "Workspace",
                        "perms": {
                            "add": True,
                            "change": True,
                            "delete": True,
                            "view": True,
                        },
                        "admin_url": admin_url("admin:core_workspace_changelist"),
                        "add_url": admin_url("admin:core_workspace_add"),
                        "view_only": False,
                    },
                    {
                        "model": FeedGroup,
                        "name": "Feed Groups",
                        "object_name": "FeedGroup",
                        "perms": {
                            "add": True,
                            "change": True,
                            "delete": True,
                            "view": True,
                        },
                        "admin_url": admin_url("admin:core_feedgroup_changelist"),
                        "add_url": admin_url("admin:core_feedgroup_add"),
                        "view_only": False,
                    },
                    {
                        "model": Tag,
                        "name": "Tags",
                        "object_name": "Tag",
                        "perms": {
                            "add": True,
                            "change": True,
                            "delete": True,
                            "view": True,
                        },
                        "admin_url": admin_url("admin:core_tag_changelist"),
                        "add_url": admin_url("admin:core_tag_add"),
                        "view_only": False,
                    },
                    {
                        "model": Digest,
                        "name": "Digests",
                        "object_name": "Digest",
                        "perms": {
                            "add": True,
                            "change": True,
                            "delete": True,
                            "view": True,
                        },
                        "admin_url": admin_url("admin:core_digest_changelist"),
                        "add_url": admin_url("admin:core_digest_add"),
                        "view_only": False,
                    },
                ],
            },
            {
                "name": "",
                "app_label": "core",
                # "app_url": "/agent/",
                # "has_module_perms": True,
                "models": [
                    {
                        # "model": " 'core.models.agent.DeepLAgent",
                        "name": _("Agents"),
                        "object_name": "Agent",
                        "admin_url": admin_url("admin:agent_list"),
                        "add_url": admin_url("admin:agent_add"),
                        # "view_only": False,
                    },
                    {
                        "model": Filter,
                        "name": "Filters",
                        "object_name": "Filter",
                        "perms": {
                            "add": True,
                            "change": True,
                            "delete": True,
                            "view": True,
                        },
                        "admin_url": admin_url("admin:core_filter_changelist"),
                        "add_url": admin_url("admin:core_filter_add"),
                        "view_only": False,
                    },
                ],
            },
        ]

        # Add User and Group models if USER_MANAGEMENT is enabled
        if settings.USER_MANAGEMENT:
            app_list.append(
                {
                    "name": "",
                    "app_label": "auth",
                    "app_url": "/auth/",
                    "has_module_perms": True,
                    "models": [
                        {
                            "model": User,
                            "name": "Users",
                            "object_name": "User",
                            "perms": {
                                "add": True,
                                "change": True,
                                "delete": True,
                                "view": True,
                            },
                            "admin_url": admin_url("admin:auth_user_changelist"),
                            "add_url": admin_url("admin:auth_user_add"),
                            "view_only": False,
                        },
                        {
                            "model": Group,
                            "name": "Groups",
                            "object_name": "Group",
                            "perms": {
                                "add": True,
                                "change": True,
                                "delete": True,
                                "view": True,
                            },
                            "admin_url": admin_url("admin:auth_group_changelist"),
                            "add_url": admin_url("admin:auth_group_add"),
                            "view_only": False,
                        },
                    ],
                }
            )

        return app_list


class AgentPaginator(Paginator):
    def __init__(self):
        super().__init__(self, 100)

        self.agent_count = 3 if settings.DEBUG else 2

    @property
    def count(self):
        return self.agent_count

    def page(self, number):
        limit = self.per_page
        offset = (number - 1) * self.per_page
        return self._get_page(
            self.enqueued_items(limit, offset),
            number,
            self,
        )

    # Copied from Huey's SqliteStorage with some modifications to allow pagination
    def enqueued_items(self, limit, offset):
        agents = (
            [OpenAIAgent, DeepLAgent, LibreTranslateAgent, TestAgent]
            if settings.DEBUG
            else [OpenAIAgent, DeepLAgent, LibreTranslateAgent]
        )
        agent_list = []
        for model in agents:
            objects = (
                model.objects.all()
                .order_by("name")
                .values_list("id", "name", "valid")[offset : offset + limit]
            )
            for obj_id, obj_name, obj_valid in objects:
                agent_list.append(
                    {
                        "id": obj_id,
                        "table_name": model._meta.db_table.split("_")[1],
                        "name": obj_name,
                        "valid": status_icon(obj_valid),
                        "provider": model._meta.verbose_name,
                    }
                )

        return agent_list


def agent_list(request):
    page_number = int(request.GET.get("p", 1))
    paginator = AgentPaginator()
    page = paginator.get_page(page_number)
    page_range = paginator.get_elided_page_range(page_number, on_each_side=2, on_ends=2)

    context = {
        **core_admin_site.each_context(request),
        "title": "Agent",
        "page": page,
        "page_range": page_range,
        "agents": page.object_list,
    }
    return render(request, "admin/agent.html", context)


def agent_add(request):
    if request.method == "POST":
        agent_name = request.POST.get("agent_name", "")
        target = f"/admin/core/{agent_name}/add" if agent_name else "/admin/"
        return (
            redirect(target)
            if url_has_allowed_host_and_scheme(target, allowed_hosts=None)
            else redirect("/")
        )
    else:
        models = (
            [OpenAIAgent, DeepLAgent, LibreTranslateAgent, TestAgent]
            if settings.DEBUG
            else [OpenAIAgent, DeepLAgent, LibreTranslateAgent]
        )
        agent_list = []
        for model in models:
            agent_list.append(
                {
                    "table_name": model._meta.db_table.split("_")[1],
                    "provider": model._meta.verbose_name,
                }
            )
        context = {
            **core_admin_site.each_context(request),
            "agent_choices": agent_list,
        }
        return render(request, "admin/agent_add.html", context)


core_admin_site = CoreAdminSite()

if settings.USER_MANAGEMENT:
    core_admin_site.register(User)
    core_admin_site.register(Group)
