import logging
from urllib.parse import urlencode
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, StreamingHttpResponse, JsonResponse
from django.utils.encoding import smart_str
from django.utils import timezone
from django.core.cache import cache
from django.views.decorators.http import condition
from django.views.decorators.http import require_http_methods
from .models import (
    Feed,
    Tag,
    Digest,
    Workspace,
    FeedGroup,
    OpenAIAgent,
    WorkspaceMembership,
)
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q
from lxml import etree
from django.utils.translation import activate, gettext_lazy as _
from feed2json import feed2json
import mistune

from .cache import cache_rss, cache_tag, cache_digest, cache_group, cache_workspace
from .actions import export_group_feeds_as_opml, export_workspace_feeds_as_opml
from .tasks.task_manager import task_manager
from .tasks.async_jobs import submit_async_task
from .forms import (
    HubBulkEditForm,
    HubBulkExportForm,
    HubFeedCreateForm,
    HubFeedEditForm,
    HubLoginForm,
    HubPasswordChangeForm,
    HubUiPreferenceForm,
    HubUserCreateForm,
    HubWorkspaceCreateForm,
    HubWorkspaceMemberRoleForm,
    HubWorkspaceProviderForm,
)

logger = logging.getLogger(__name__)


def _hub_redirect():
    return redirect("hub:dashboard")


def _hub_language(request):
    session = getattr(request, "session", None)
    if session is None:
        return "zh-hans"
    return session.get("hub_ui_language", "zh-hans")


def _hub_theme(request):
    session = getattr(request, "session", None)
    if session is None:
        return "system"
    return session.get("hub_theme", "system")


def _effective_feed_label(feed):
    return feed.name or feed.feed_url or feed.slug or f"feed-{feed.pk}"


def _hub_login_url(request):
    activate(_hub_language(request))
    query = urlencode({"next": request.get_full_path()})
    return f"/login/?{query}"


def _hub_accessible_workspaces(request):
    queryset = Workspace.objects.filter(is_active=True)
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset.order_by("name")
    return (
        queryset.filter(memberships__user=user, memberships__is_active=True)
        .distinct()
        .order_by("name")
    )


def _workspace_membership_map(request, workspaces):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    if user.is_superuser:
        return {workspace.id: "owner" for workspace in workspaces}
    memberships = WorkspaceMembership.objects.filter(
        user=user,
        is_active=True,
        workspace__in=workspaces,
    ).values_list("workspace_id", "role")
    return {workspace_id: role for workspace_id, role in memberships}


def _can_manage_workspace(request, workspace, membership_map=None):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    membership_map = membership_map or {}
    return membership_map.get(workspace.id) in WorkspaceMembership.MANAGE_ROLES


def _feed_queryset_for_hub(request, workspace_queryset):
    queryset = (
        Feed.objects.select_related("workspace")
        .prefetch_related("groups", "tags")
        .filter(workspace__in=workspace_queryset)
        .order_by("workspace__name", "name", "id")
    )
    search = (request.GET.get("q") or "").strip()
    workspace_slug = (request.GET.get("workspace") or "").strip()
    group_slug = (request.GET.get("group") or "").strip()
    source_kind = (request.GET.get("source_kind") or "").strip()
    archived = (request.GET.get("archived") or "active").strip()

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(feed_url__icontains=search)
            | Q(source_ref__icontains=search)
            | Q(slug__icontains=search)
        )
    if workspace_slug:
        queryset = queryset.filter(workspace__slug=workspace_slug)
    if group_slug:
        queryset = queryset.filter(groups__slug=group_slug)
    if source_kind:
        queryset = queryset.filter(source_kind=source_kind)
    if archived == "only":
        queryset = queryset.filter(is_archived=True)
    elif archived != "all":
        queryset = queryset.filter(is_archived=False)

    return queryset.distinct(), {
        "q": search,
        "workspace": workspace_slug,
        "group": group_slug,
        "source_kind": source_kind,
        "archived": archived,
    }


def _render_feed_links(feeds, variant):
    lines = [feed.get_subscription_url(variant) for feed in feeds]
    response = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="rsshub-{variant}-feeds.txt"'
    )
    return response


def _selected_feed_for_dashboard(request, feeds):
    feed_id = (request.GET.get("feed") or "").strip()
    if not feed_id.isdigit():
        return feeds.first()
    return feeds.filter(id=int(feed_id)).first() or feeds.first()


def _workspace_for_dashboard(request, workspaces, selected_feed=None):
    workspace_slug = (request.GET.get("workspace") or "").strip()
    if workspace_slug:
        workspace = workspaces.filter(slug=workspace_slug).first()
        if workspace:
            return workspace
    if selected_feed:
        return selected_feed.workspace
    return workspaces.first()


def _tag_queryset_for_hub(workspace_queryset):
    return Tag.objects.filter(feeds__workspace__in=workspace_queryset).distinct()


def _member_queryset_for_workspace(selected_workspace):
    if not selected_workspace:
        return WorkspaceMembership.objects.none()
    return (
        WorkspaceMembership.objects.select_related("user")
        .filter(workspace=selected_workspace, is_active=True)
        .order_by("role", "user__username")
    )


def _role_choices_for_manager(can_assign_owner):
    choices = []
    for value, label in WorkspaceMembership.ROLE_CHOICES:
        if value == WorkspaceMembership.OWNER and not can_assign_owner:
            continue
        choices.append((value, label))
    return choices


def _member_role_forms(selected_workspace, member_list, ui_language, can_manage, request):
    if not selected_workspace or not can_manage:
        return {}
    membership_map = _workspace_membership_map(request, [selected_workspace])
    forms = {}
    for membership in member_list:
        if not _can_manage_workspace_member(request, membership, membership_map):
            continue
        role_choices = _role_choices_for_manager(
            _can_assign_owner_role(request, selected_workspace, membership_map)
        )
        forms[membership.id] = HubWorkspaceMemberRoleForm(
            initial={"role": membership.role},
            ui_language=ui_language,
            role_choices=role_choices,
        )
    return forms


def _member_rows(selected_workspace, member_list, ui_language, can_manage, request):
    membership_map = (
        _workspace_membership_map(request, [selected_workspace])
        if selected_workspace
        else {}
    )
    role_forms = _member_role_forms(
        selected_workspace,
        member_list,
        ui_language,
        can_manage,
        request,
    )
    return [
        {
            "membership": membership,
            "role_form": role_forms.get(membership.id),
            "can_manage": _can_manage_workspace_member(request, membership, membership_map),
            "can_remove": not (
                membership.role == WorkspaceMembership.OWNER
                and _active_owner_count(membership.workspace) <= 1
            ),
        }
        for membership in member_list
    ]


def _workspace_member_management_allowed(request, workspace, membership_map=None):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    membership_map = membership_map or {}
    return membership_map.get(workspace.id) in WorkspaceMembership.MANAGE_ROLES


def _can_assign_owner_role(request, workspace, membership_map=None):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    membership_map = membership_map or {}
    return membership_map.get(workspace.id) == WorkspaceMembership.OWNER


def _can_manage_workspace_member(request, target_membership, membership_map=None):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    membership_map = membership_map or {}
    actor_role = membership_map.get(target_membership.workspace_id)
    if actor_role == WorkspaceMembership.OWNER:
        return True
    if actor_role == WorkspaceMembership.MANAGER:
        return target_membership.role != WorkspaceMembership.OWNER
    return False


def _active_owner_count(workspace):
    return WorkspaceMembership.objects.filter(
        workspace=workspace,
        is_active=True,
        role=WorkspaceMembership.OWNER,
    ).count()


def _login_required_hub(view_func):
    def wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return redirect(_hub_login_url(request))
        return view_func(request, *args, **kwargs)

    return wrapped


@_login_required_hub
def hub_dashboard(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    if not workspaces.exists():
        return render(
            request,
            "hub/dashboard.html",
            {
                "feeds": Feed.objects.none(),
                "workspaces": workspaces,
                "groups": FeedGroup.objects.none(),
                "filters": {
                    "q": "",
                    "workspace": "",
                    "group": "",
                    "source_kind": "",
                    "archived": "active",
                },
                "create_form": None,
                "export_form": None,
                "bulk_edit_form": None,
                "feed_edit_form": None,
                "selected_feed": None,
                "selected_workspace": None,
                "workspace_create_form": HubWorkspaceCreateForm(
                    ui_language=ui_language,
                ),
                "workspace_provider_form": None,
                "ui_preference_form": HubUiPreferenceForm(
                    initial={
                        "ui_language": ui_language,
                        "theme": _hub_theme(request),
                    },
                    ui_language=ui_language,
                ),
                "source_kind_choices": Feed.SOURCE_KIND_CHOICES,
                "selected_group": "",
                "ui_language": ui_language,
                "theme": _hub_theme(request),
                "membership_map": {},
                "selected_workspace_role": None,
                "member_list": [],
                "member_rows": [],
                "member_create_form": None,
                "password_form": HubPasswordChangeForm(
                    user=request.user,
                    ui_language=ui_language,
                ),
                "hub_user": request.user,
                "can_manage_selected_workspace": False,
                "can_manage_workspace_members": False,
                "has_workspace_access": False,
            },
        )

    feeds, filters = _feed_queryset_for_hub(request, workspaces)
    groups = FeedGroup.objects.select_related("workspace").filter(
        workspace__in=workspaces
    ).order_by(
        "workspace__name", "name"
    )
    selected_feed = _selected_feed_for_dashboard(request, feeds)
    selected_workspace = _workspace_for_dashboard(request, workspaces, selected_feed)
    tag_queryset = _tag_queryset_for_hub(workspaces)
    membership_map = _workspace_membership_map(request, workspaces)
    selected_workspace_role = (
        membership_map.get(selected_workspace.id) if selected_workspace else None
    )
    can_manage_selected_workspace = (
        _can_manage_workspace(request, selected_workspace, membership_map)
        if selected_workspace
        else False
    )

    create_form = HubFeedCreateForm(
        initial={"workspace": selected_workspace},
        ui_language=ui_language,
        workspace_queryset=workspaces,
    )
    export_form = HubBulkExportForm(ui_language=ui_language)
    bulk_edit_form = HubBulkEditForm(
        ui_language=ui_language,
        workspace_queryset=workspaces,
        tag_queryset=tag_queryset,
    )
    if selected_feed:
        feed_edit_form = HubFeedEditForm(
            instance=selected_feed,
            ui_language=ui_language,
            tag_queryset=tag_queryset,
        )
    else:
        feed_edit_form = None
    workspace_create_form = HubWorkspaceCreateForm(ui_language=ui_language)
    workspace_provider_form = HubWorkspaceProviderForm(
        ui_language=ui_language,
        workspace_queryset=workspaces,
    )
    if selected_workspace:
        workspace_provider_form.set_workspace_initial(selected_workspace)
    ui_preference_form = HubUiPreferenceForm(
        initial={
            "ui_language": ui_language,
            "theme": _hub_theme(request),
        },
        ui_language=ui_language,
    )
    member_list = list(_member_queryset_for_workspace(selected_workspace))
    can_manage_workspace_members = (
        _workspace_member_management_allowed(request, selected_workspace, membership_map)
        if selected_workspace
        else False
    )
    can_assign_owner_role = (
        _can_assign_owner_role(request, selected_workspace, membership_map)
        if selected_workspace
        else False
    )
    member_create_form = (
        HubUserCreateForm(
            ui_language=ui_language,
            role_choices=_role_choices_for_manager(can_assign_owner_role),
        )
        if can_manage_workspace_members
        else None
    )
    password_form = HubPasswordChangeForm(user=request.user, ui_language=ui_language)
    context = {
        "feeds": feeds,
        "workspaces": workspaces,
        "groups": groups,
        "filters": filters,
        "create_form": create_form,
        "export_form": export_form,
        "bulk_edit_form": bulk_edit_form,
        "feed_edit_form": feed_edit_form,
        "selected_feed": selected_feed,
        "selected_workspace": selected_workspace,
        "workspace_create_form": workspace_create_form,
        "workspace_provider_form": workspace_provider_form,
        "ui_preference_form": ui_preference_form,
        "source_kind_choices": Feed.SOURCE_KIND_CHOICES,
        "selected_group": filters["group"],
        "ui_language": ui_language,
        "theme": _hub_theme(request),
        "membership_map": membership_map,
        "selected_workspace_role": selected_workspace_role,
        "member_list": member_list,
        "member_rows": _member_rows(
            selected_workspace,
            member_list,
            ui_language,
            can_manage_workspace_members,
            request,
        ),
        "member_create_form": member_create_form,
        "password_form": password_form,
        "hub_user": request.user,
        "can_manage_selected_workspace": can_manage_selected_workspace,
        "can_manage_workspace_members": can_manage_workspace_members,
        "has_workspace_access": True,
    }
    return render(request, "hub/dashboard.html", context)


@require_http_methods(["GET", "POST"])
def hub_login(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    if request.user.is_authenticated:
        return _hub_redirect()
    form = HubLoginForm(request, data=request.POST or None, ui_language=ui_language)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        request.session["hub_ui_language"] = ui_language
        target = request.POST.get("next") or request.GET.get("next") or _hub_redirect().url
        return redirect(target)
    return render(
        request,
        "hub/login.html",
        {
            "form": form,
            "next_url": request.GET.get("next") or request.POST.get("next") or _hub_redirect().url,
            "ui_language": ui_language,
            "theme": _hub_theme(request),
        },
    )


@require_http_methods(["POST"])
def hub_logout(request):
    logout(request)
    messages.success(
        request,
        _("Signed out successfully.") if _hub_language(request) == "en-us" else _("已退出登录。"),
    )
    return redirect("hub:login")


@_login_required_hub
@require_http_methods(["POST"])
def hub_create_workspace(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    form = HubWorkspaceCreateForm(request.POST, ui_language=ui_language)
    if form.is_valid():
        workspace = form.save()
        WorkspaceMembership.objects.create(
            user=request.user,
            workspace=workspace,
            role=WorkspaceMembership.OWNER,
        )
        messages.success(
            request,
            _("Created workspace {}.").format(workspace.name),
        )
        return redirect(f"{_hub_redirect().url}?workspace={workspace.slug}")

    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, f"{field}: {error}")
    return _hub_redirect()


@_login_required_hub
@require_http_methods(["POST"])
def hub_create_feed(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    form = HubFeedCreateForm(
        request.POST,
        ui_language=ui_language,
        workspace_queryset=workspaces,
    )
    if form.is_valid():
        feed = form.save()
        messages.success(
            request,
            _("Feed created: {}").format(feed.name or feed.feed_url or feed.slug),
        )
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return _hub_redirect()


@_login_required_hub
@require_http_methods(["POST"])
def hub_update_feed(request, feed_id: int):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    feed = get_object_or_404(
        Feed.objects.select_related("workspace").prefetch_related("groups", "tags"),
        pk=feed_id,
        workspace__in=workspaces,
    )
    form = HubFeedEditForm(
        request.POST,
        instance=feed,
        ui_language=ui_language,
        tag_queryset=_tag_queryset_for_hub(workspaces),
    )
    if form.is_valid():
        updated_feed = form.save()
        messages.success(
            request,
            _("Feed updated: {}").format(_effective_feed_label(updated_feed)),
        )
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return redirect(f"{_hub_redirect().url}?feed={feed_id}&workspace={feed.workspace.slug}")


@_login_required_hub
@require_http_methods(["POST"])
def hub_import_opml(request):
    workspace_id = request.POST.get("workspace")
    workspaces = _hub_accessible_workspaces(request)
    if workspace_id and not workspaces.filter(pk=workspace_id).exists():
        messages.error(request, _("You cannot import into that workspace."))
        return _hub_redirect()
    response = import_opml(request)
    if response.status_code == 302:
        return _hub_redirect()
    return response


@_login_required_hub
@require_http_methods(["POST"])
def hub_bulk_export(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    form = HubBulkExportForm(request.POST, ui_language=ui_language)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
        return _hub_redirect()

    raw_ids = form.cleaned_data["selected_feeds"]
    selected_ids = [int(item) for item in raw_ids.split(",") if item.strip().isdigit()]
    feeds = Feed.objects.filter(
        id__in=selected_ids,
        workspace__in=_hub_accessible_workspaces(request),
    ).order_by("name", "id")
    if not feeds.exists():
        messages.error(request, _("No feeds selected for export."))
        return _hub_redirect()

    variant = form.cleaned_data["export_variant"]
    export_format = form.cleaned_data["export_format"]

    if export_format == "links":
        return _render_feed_links(feeds, variant)

    title_prefix = f"RSSHub {variant.title()} Feeds"
    filename_prefix = f"rsshub_{variant}"
    if variant == "proxy":
        get_feed_url_func = lambda feed: feed.get_proxy_feed_url()
    else:
        get_feed_url_func = lambda feed: feed.get_translated_feed_url()

    from .actions import _generate_opml_feed

    return _generate_opml_feed(
        title_prefix=title_prefix,
        queryset=feeds,
        get_feed_url_func=get_feed_url_func,
        filename_prefix=filename_prefix,
        group_by="groups",
    )


def _selected_feed_ids(form):
    raw_ids = form.cleaned_data["selected_feeds"]
    return [int(item) for item in raw_ids.split(",") if item.strip().isdigit()]


@_login_required_hub
@require_http_methods(["POST"])
def hub_bulk_edit(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    form = HubBulkEditForm(
        request.POST,
        ui_language=ui_language,
        workspace_queryset=workspaces,
        tag_queryset=_tag_queryset_for_hub(workspaces),
    )
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
        return _hub_redirect()

    selected_ids = _selected_feed_ids(form)
    feeds = list(
        Feed.objects.select_related("workspace")
        .prefetch_related("groups", "tags")
        .filter(id__in=selected_ids, workspace__in=workspaces)
    )
    if not feeds:
        messages.error(request, _("No feeds selected for editing."))
        return _hub_redirect()

    record_action = form.cleaned_data["record_action"]
    if record_action == "delete":
        deleted_count = len(feeds)
        Feed.objects.filter(id__in=selected_ids).delete()
        messages.success(request, _("Deleted {} feeds.").format(deleted_count))
        return _hub_redirect()

    if record_action == "archive":
        Feed.objects.filter(id__in=selected_ids).update(is_archived=True)
    elif record_action == "unarchive":
        Feed.objects.filter(id__in=selected_ids).update(is_archived=False)

    translation_display = form.cleaned_data.get("translation_display")
    if translation_display is not None:
        Feed.objects.filter(id__in=selected_ids).update(
            translation_display=translation_display
        )

    provider_mode = form.cleaned_data["provider_mode"]
    translator_value = form.cleaned_data.get("translator_option")
    summarizer = form.cleaned_data.get("summarizer")
    if provider_mode == "workspace_default":
        Feed.objects.filter(id__in=selected_ids).update(
            translator_content_type_id=None,
            translator_object_id=None,
            summarizer_id=None,
        )
    elif provider_mode == "override":
        content_type_id = None
        object_id = None
        if translator_value:
            content_type_id, object_id = map(int, translator_value.split(":"))
        Feed.objects.filter(id__in=selected_ids).update(
            translator_content_type_id=content_type_id,
            translator_object_id=object_id,
            summarizer_id=summarizer.id if summarizer else None,
        )

    group_mode = form.cleaned_data["group_mode"]
    groups = list(form.cleaned_data["groups"])
    tag_mode = form.cleaned_data["tag_mode"]
    tags = list(form.cleaned_data["tags"])
    if groups:
        workspace_ids = {group.workspace_id for group in groups}
        for feed in feeds:
            if any(workspace_id != feed.workspace_id for workspace_id in workspace_ids):
                messages.error(
                    request,
                    _(
                        "Selected groups must stay within each feed's workspace."
                    ),
                )
                return _hub_redirect()
    for feed in feeds:
        if group_mode == "replace":
            feed.groups.set(groups)
        elif group_mode == "add":
            feed.groups.add(*groups)
        elif group_mode == "remove" and groups:
            feed.groups.remove(*groups)

        if tag_mode == "replace":
            feed.tags.set(tags)
        elif tag_mode == "add":
            feed.tags.add(*tags)
        elif tag_mode == "remove" and tags:
            feed.tags.remove(*tags)

    messages.success(
        request,
        _("Updated {} selected feeds.").format(len(feeds)),
    )
    return _hub_redirect()


@_login_required_hub
@require_http_methods(["POST"])
def hub_update_workspace_providers(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    form = HubWorkspaceProviderForm(
        request.POST,
        ui_language=ui_language,
        workspace_queryset=workspaces,
    )
    if form.is_valid():
        workspace = form.cleaned_data["workspace"]
        if not _can_manage_workspace(
            request,
            workspace,
            _workspace_membership_map(request, workspaces),
        ):
            messages.error(request, _("You do not have permission to edit that workspace."))
            return _hub_redirect()
        workspace = form.save()
        messages.success(
            request,
            _("Workspace defaults updated: {}").format(workspace.name),
        )
        return redirect(f"{_hub_redirect().url}?workspace={workspace.slug}")

    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, f"{field}: {error}")
    return _hub_redirect()


@_login_required_hub
@require_http_methods(["POST"])
def hub_set_preferences(request):
    form = HubUiPreferenceForm(request.POST, ui_language=_hub_language(request))
    if form.is_valid():
        request.session["hub_ui_language"] = form.cleaned_data["ui_language"]
        request.session["hub_theme"] = form.cleaned_data["theme"]
        activate(form.cleaned_data["ui_language"])
    return _hub_redirect()


@_login_required_hub
@require_http_methods(["POST"])
def hub_refresh_feed(request, feed_id: int):
    activate(_hub_language(request))
    feed = get_object_or_404(
        Feed,
        pk=feed_id,
        workspace__in=_hub_accessible_workspaces(request),
    )
    feed.fetch_status = None
    feed.translation_status = None
    feed.save(update_fields=["fetch_status", "translation_status"])

    submit_async_task(
        f"hub_refresh_feed_{feed.slug}",
        "core.jobs.refresh_feed_job",
        feed.id,
    )
    messages.success(
        request,
        _("Refresh scheduled: {}").format(_effective_feed_label(feed)),
    )
    return redirect(f"{_hub_redirect().url}?feed={feed.id}&workspace={feed.workspace.slug}")


@_login_required_hub
@require_http_methods(["POST"])
def hub_change_password(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    form = HubPasswordChangeForm(
        request.user,
        request.POST,
        ui_language=ui_language,
    )
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(
            request,
            _("Password updated successfully.")
            if ui_language == "en-us"
            else _("密码已更新。"),
        )
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return _hub_redirect()


@_login_required_hub
@require_http_methods(["POST"])
def hub_create_workspace_user(request):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    workspace_slug = (request.POST.get("workspace_slug") or "").strip()
    workspace = get_object_or_404(workspaces, slug=workspace_slug)
    membership_map = _workspace_membership_map(request, workspaces)
    if not _workspace_member_management_allowed(request, workspace, membership_map):
        messages.error(request, _("You do not have permission to manage that workspace."))
        return _hub_redirect()
    form = HubUserCreateForm(
        request.POST,
        ui_language=ui_language,
        role_choices=_role_choices_for_manager(
            _can_assign_owner_role(request, workspace, membership_map)
        ),
    )
    if form.is_valid():
        user = form.save()
        WorkspaceMembership.objects.create(
            user=user,
            workspace=workspace,
            role=form.cleaned_data["role"],
        )
        messages.success(
            request,
            _("Created member {} in {}.").format(user.username, workspace.name),
        )
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return redirect(f"{_hub_redirect().url}?workspace={workspace.slug}")


@_login_required_hub
@require_http_methods(["POST"])
def hub_update_workspace_member(request, membership_id: int):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    membership = get_object_or_404(
        WorkspaceMembership.objects.select_related("workspace", "user"),
        pk=membership_id,
        workspace__in=workspaces,
        is_active=True,
    )
    membership_map = _workspace_membership_map(request, workspaces)
    if not _can_manage_workspace_member(request, membership, membership_map):
        messages.error(request, _("You do not have permission to manage that workspace."))
        return _hub_redirect()

    form = HubWorkspaceMemberRoleForm(
        request.POST,
        ui_language=ui_language,
        role_choices=_role_choices_for_manager(
            _can_assign_owner_role(request, membership.workspace, membership_map)
        ),
    )
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
        return redirect(f"{_hub_redirect().url}?workspace={membership.workspace.slug}")

    new_role = form.cleaned_data["role"]
    if (
        membership.role == WorkspaceMembership.OWNER
        and new_role != WorkspaceMembership.OWNER
        and _active_owner_count(membership.workspace) <= 1
    ):
        messages.error(
            request,
            _("At least one active owner must remain in the workspace."),
        )
        return redirect(f"{_hub_redirect().url}?workspace={membership.workspace.slug}")

    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    messages.success(
        request,
        _("Updated {} to {}.").format(
            membership.user.username,
            membership.get_role_display(),
        ),
    )
    return redirect(f"{_hub_redirect().url}?workspace={membership.workspace.slug}")


@_login_required_hub
@require_http_methods(["POST"])
def hub_remove_workspace_member(request, membership_id: int):
    ui_language = _hub_language(request)
    activate(ui_language)
    workspaces = _hub_accessible_workspaces(request)
    membership = get_object_or_404(
        WorkspaceMembership.objects.select_related("workspace", "user"),
        pk=membership_id,
        workspace__in=workspaces,
        is_active=True,
    )
    membership_map = _workspace_membership_map(request, workspaces)
    if not _can_manage_workspace_member(request, membership, membership_map):
        messages.error(request, _("You do not have permission to manage that workspace."))
        return _hub_redirect()

    if (
        membership.role == WorkspaceMembership.OWNER
        and _active_owner_count(membership.workspace) <= 1
    ):
        messages.error(
            request,
            _("At least one active owner must remain in the workspace."),
        )
        return redirect(f"{_hub_redirect().url}?workspace={membership.workspace.slug}")

    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        _("Removed {} from {}.").format(
            membership.user.username,
            membership.workspace.name,
        ),
    )
    return redirect(f"{_hub_redirect().url}?workspace={membership.workspace.slug}")


def _get_modified(request, feed_slug, feed_type="t", **kwargs):
    try:
        if feed_type == "t":
            modified = Feed.objects.get(slug=feed_slug).last_translate
        else:
            modified = Feed.objects.get(slug=feed_slug).last_fetch
    except Feed.DoesNotExist:
        logger.warning(
            "Translated feed not found, Maybe still in progress, Please confirm it's exist: %s",
            feed_slug,
        )
        modified = None
    return modified


def _get_etag(request, feed_slug, feed_type="t", **kwargs):
    try:
        if feed_type == "t":
            last_translate = Feed.objects.get(slug=feed_slug).last_translate
            etag = last_translate.isoformat() if last_translate else None
        else:
            etag = Feed.objects.get(slug=feed_slug).etag
    except Feed.DoesNotExist:
        logger.warning(
            "Feed not fetched yet, Please update it first: %s",
            feed_slug,
        )
        etag = None
    return etag


def _make_response(atom_feed, filename, format="xml"):
    if format == "json":
        # 如果需要返回 JSON 格式
        if not atom_feed:
            return JsonResponse({"error": "No feed data available"}, status=404)
        feed_json = feed2json(atom_feed)
        response = JsonResponse(feed_json)
    else:
        # 使用生成器函数实现流式传输
        def stream_content():
            if not atom_feed:
                yield b"<error>No feed data available</error>"
                return
            chunk_size = 4096  # 每次发送4KB
            for i in range(0, len(atom_feed), chunk_size):
                yield atom_feed[i : i + chunk_size]

        response = StreamingHttpResponse(
            stream_content(),  # 使用生成器
            content_type="application/xml; charset=utf-8",
        )
        response["Content-Disposition"] = f"inline; filename={filename}.xml"
    return response


def _get_digest_modified(request, slug: str, **kwargs):
    try:
        digest = Digest.objects.get(slug=slug)
        return digest.last_generated
    except Digest.DoesNotExist:
        return None


def _get_digest_etag(request, slug: str, **kwargs):
    try:
        digest = Digest.objects.get(slug=slug)
        return digest.last_generated.isoformat() if digest.last_generated else None
    except Digest.DoesNotExist:
        return None


def import_opml(request):
    if request.method == "POST":
        opml_file = request.FILES.get("opml_file")
        workspace_id = request.POST.get("workspace")
        create_groups = request.POST.get("create_groups_from_outlines") == "on"
        workspace = (
            Workspace.objects.filter(pk=workspace_id).first()
            if workspace_id
            else Workspace.get_default()
        )
        if opml_file and isinstance(opml_file, InMemoryUploadedFile):
            try:
                # 直接读取字节数据（lxml 支持二进制解析）
                opml_content = opml_file.read()

                # 使用安全的 lxml 解析器解析 OPML
                parser = etree.XMLParser(resolve_entities=False)
                root = etree.fromstring(opml_content, parser=parser)
                body = root.find("body")

                if body is None:
                    messages.error(request, _("Invalid OPML: Missing body element"))
                    return redirect("admin:core_feed_changelist")

                # 递归处理所有 outline 节点
                def process_outlines(outlines, tag: str = None, parent_group=None):
                    for outline in outlines:
                        # 检查是否为 feed（有 xmlUrl 属性）
                        if "xmlUrl" in outline.attrib:
                            feed, created = Feed.objects.get_or_create(
                                workspace=workspace,
                                feed_url=outline.get("xmlUrl"),
                                defaults={
                                    "name": outline.get("title") or outline.get("text"),
                                    "workspace": workspace,
                                    "target_language": workspace.default_target_language,
                                },
                            )
                            if tag:
                                tag_obj, _ = Tag.objects.get_or_create(name=tag)
                                feed.tags.add(tag_obj)
                            if parent_group:
                                feed.groups.add(parent_group)
                        # 处理嵌套结构（新类别）
                        elif outline.find("outline") is not None:
                            new_tag = outline.get("text") or outline.get("title")
                            group = None
                            if create_groups and new_tag:
                                group, _ = FeedGroup.objects.get_or_create(
                                    workspace=workspace,
                                    name=new_tag,
                                )
                            process_outlines(
                                outline.findall("outline"),
                                new_tag,
                                group,
                            )

                # 从 body 开始处理顶级 outline
                process_outlines(body.findall("outline"))

                messages.success(request, _("OPML file imported successfully."))
            except etree.XMLSyntaxError as e:
                messages.error(request, _("XML syntax error: {}").format(str(e)))
            except Exception as e:
                messages.error(
                    request, _("Error importing OPML file: {}").format(str(e))
                )
        else:
            messages.error(request, _("Please upload a valid OPML file."))

    return redirect("admin:core_feed_changelist")


def workspace_feed(request, workspace_slug: str, feed_type="t", format="xml"):
    workspace_slug = smart_str(workspace_slug)
    try:
        cache_key = f"cache_workspace_{workspace_slug}_{feed_type}_{format}"
        content = cache.get(cache_key)
        if content is None:
            content = cache_workspace(workspace_slug, feed_type, format)
        return _make_response(content, workspace_slug, format)
    except Exception as e:
        logger.warning(f"Workspace feed not found {workspace_slug}: {str(e)}")
        return HttpResponse(status=404, content="Workspace feed not found.")


def group_feed(request, workspace_slug: str, group_slug: str, feed_type="t", format="xml"):
    workspace_slug = smart_str(workspace_slug)
    group_slug = smart_str(group_slug)
    try:
        cache_key = f"cache_group_{workspace_slug}_{group_slug}_{feed_type}_{format}"
        content = cache.get(cache_key)
        if content is None:
            content = cache_group(workspace_slug, group_slug, feed_type, format)
        return _make_response(content, f"{workspace_slug}-{group_slug}", format)
    except Exception as e:
        logger.warning(f"Group feed not found {workspace_slug}/{group_slug}: {str(e)}")
        return HttpResponse(status=404, content="Group feed not found.")


def workspace_opml(request, workspace_slug: str, variant: str = "translated"):
    workspace = get_object_or_404(Workspace, slug=workspace_slug)
    return export_workspace_feeds_as_opml(workspace, variant)


def group_opml(request, workspace_slug: str, group_slug: str, variant: str = "translated"):
    group = get_object_or_404(
        FeedGroup, workspace__slug=workspace_slug, slug=group_slug
    )
    return export_group_feeds_as_opml(group, variant)


@condition(etag_func=_get_etag, last_modified_func=_get_modified)
def rss(request, feed_slug, feed_type="t", format="xml"):
    # Sanitize the feed_slug to prevent path traversal attacks
    feed_slug = smart_str(feed_slug)
    try:
        cache_key = f"cache_rss_{feed_slug}_{feed_type}_{format}"
        content = cache.get(cache_key)
        if content is None:
            logger.debug(f"Cache MISS for key: {cache_key}")
            content = cache_rss(feed_slug, feed_type, format)
        else:
            logger.debug(f"Cache HIT for key: {cache_key}")

        return _make_response(content, feed_slug, format)
    except Exception as e:
        logger.warning(f"Feed not found {feed_slug}: {str(e)}")
        return HttpResponse(
            status=404,
            content="Feed not found, Maybe it's still in progress, Please try again later.",
        )


def tag(request, tag: str, feed_type="t", format="xml"):
    tag = smart_str(tag)
    all_tag = list(Tag.objects.values_list("slug", flat=True))

    if tag not in all_tag:
        return HttpResponse(status=404)

    try:
        cache_key = f"cache_tag_{tag}_{feed_type}_{format}"
        content = cache.get(cache_key)
        if content is None:
            logger.debug(f"Cache MISS for key: {cache_key}")
            content = cache_tag(tag, feed_type, format)
        else:
            logger.debug(f"Cache HIT for key: {cache_key}")
        return _make_response(content, tag, format)
    except Exception as e:
        logger.warning("tag not found: %s / %s", tag, str(e))
        return HttpResponse(
            status=404,
            content="Feed not found, Maybe it's still in progress, Please try again later.",
        )


def digest_view(request, slug):
    """Display digest content as HTML page."""
    digest = get_object_or_404(Digest, slug=slug)

    # 获取最新一条摘要 Entry
    digest_feed = digest.get_digest_feed()
    latest = digest_feed.entries.order_by("-pubdate", "-id").first()
    if not latest or not latest.ai_summary:
        return HttpResponse(
            status=404,
            content="No digest content available. Please generate the digest first.",
        )

    # Convert markdown to HTML
    # md = markdown.Markdown(extensions=['extra', 'codehilite', 'tables', 'toc'])
    html_content = mistune.html(latest.ai_summary)
    
    # Format last_generated time with timezone conversion
    if digest.last_generated:
        local_time = timezone.localtime(digest.last_generated)
        generated_time = local_time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        generated_time = "Never"

    # Create HTML response
    html_response = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{digest.name}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1, h2, h3 {{
                color: #2c3e50;
            }}
            h1 {{
                border-bottom: 2px solid #3498db;
                padding-bottom: 10px;
            }}
            .meta {{
                color: #666;
                font-size: 14px;
                margin-bottom: 20px;
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }}
            a {{
                color: #3498db;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            blockquote {{
                border-left: 4px solid #3498db;
                padding-left: 15px;
                margin-left: 0;
                color: #555;
            }}
            code {{
                background-color: #f4f4f4;
                padding: 2px 4px;
                border-radius: 3px;
                font-family: Consolas, Monaco, monospace;
            }}
            pre {{
                background-color: #f4f4f4;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="meta">
                <strong>Generated:</strong> {generated_time}<br>
                <strong>Tags:</strong> {", ".join([tag.name for tag in digest.tags.all()])}<br>
                <strong>Days Range:</strong> {digest.days_range} days
            </div>
            <div class="content">
                {html_content}
            </div>
        </div>
    </body>
    </html>
    """

    return HttpResponse(html_response, content_type="text/html; charset=utf-8")


@condition(etag_func=_get_digest_etag, last_modified_func=_get_digest_modified)
def digest(request, slug, format="xml"):
    """Return digest as ATOM/JSON feed, with caching."""
    slug = smart_str(slug)
    try:
        cache_key = f"cache_digest_{slug}_{format}"
        content = cache.get(cache_key)
        if content is None:
            logger.debug(f"Cache MISS for key: {cache_key}")
            content = cache_digest(slug, format)
        else:
            logger.debug(f"Cache HIT for key: {cache_key}")

        return _make_response(content, slug, format)
    except Exception as e:
        logger.warning(f"Digest not found {slug}: {str(e)}")
        return HttpResponse(
            status=404,
            content="Digest not found, or not generated yet.",
        )
