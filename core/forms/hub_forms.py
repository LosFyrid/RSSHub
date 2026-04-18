from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from core.models import (
    Feed,
    FeedGroup,
    OpenAIAgent,
    Tag,
    Workspace,
    WorkspaceMembership,
)
from utils.modelAdmin_utils import get_all_agent_choices


def _is_english(ui_language):
    return (ui_language or "zh-hans").lower() == "en-us"


def _ui_text(ui_language, zh_value, en_value):
    return en_value if _is_english(ui_language) else zh_value


def _translation_display_choices(ui_language, include_blank=False):
    choices = []
    if include_blank:
        choices.append(
            (
                "",
                _ui_text(
                    ui_language,
                    "保持当前显示方式",
                    "Keep current display mode",
                ),
            )
        )
    choices.extend(
        [
            (
                0,
                _ui_text(
                    ui_language,
                    "仅译文",
                    "Translation only",
                ),
            ),
            (
                1,
                _ui_text(
                    ui_language,
                    "译文 | 原文",
                    "Translation | Original",
                ),
            ),
            (
                2,
                _ui_text(
                    ui_language,
                    "原文 | 译文",
                    "Original | Translation",
                ),
            ),
        ]
    )
    return choices


class HubFeedCreateForm(forms.ModelForm):
    class Meta:
        model = Feed
        fields = [
            "workspace",
            "feed_url",
            "name",
            "groups",
        ]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        workspace_queryset = kwargs.pop("workspace_queryset", None)
        super().__init__(*args, **kwargs)
        self.fields["workspace"].queryset = (workspace_queryset or Workspace.objects).filter(
            is_active=True
        ).order_by("name")
        self.fields["groups"].queryset = FeedGroup.objects.select_related(
            "workspace"
        ).filter(workspace__in=self.fields["workspace"].queryset).order_by(
            "workspace__name", "name"
        )
        self.fields["name"].required = False
        self.fields["feed_url"].widget.attrs["placeholder"] = _(
            "https://example.com/feed.xml"
        )
        self.fields["name"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "可选显示名称",
            "Optional display name",
        )

    def clean(self):
        cleaned_data = super().clean()
        workspace = cleaned_data.get("workspace")
        groups = cleaned_data.get("groups")
        feed_url = cleaned_data.get("feed_url")

        if not feed_url:
            self.add_error("feed_url", _("RSS/Atom URL is required."))

        if workspace and groups:
            mismatched = [group for group in groups if group.workspace_id != workspace.id]
            if mismatched:
                self.add_error(
                    "groups",
                    _("Selected groups must belong to the same workspace."),
                )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        workspace = self.cleaned_data["workspace"]
        instance.workspace = workspace
        instance.source_kind = Feed.TRANSLATE
        instance.target_language = workspace.default_target_language
        instance.translate_title = True
        instance.translate_content = True
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class HubFeedEditForm(forms.ModelForm):
    translator_option = forms.ChoiceField(
        choices=(),
        required=False,
        label=_("Translator Override"),
    )

    class Meta:
        model = Feed
        fields = [
            "name",
            "groups",
            "tags",
            "target_language",
            "translate_title",
            "translate_content",
            "summary",
            "fetch_article",
            "max_posts",
            "update_frequency",
            "translation_display",
            "summarizer",
            "summary_detail",
            "additional_prompt",
            "is_archived",
        ]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        tag_queryset = kwargs.pop("tag_queryset", None)
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = FeedGroup.objects.select_related(
            "workspace"
        ).order_by("workspace__name", "name")
        self.fields["tags"].queryset = (tag_queryset or Tag.objects).all().order_by("name")
        self.fields["summarizer"].queryset = OpenAIAgent.objects.filter(valid=True)
        self.fields["summarizer"].required = False
        self.fields["summarizer"].empty_label = _ui_text(
            self.ui_language,
            "使用 workspace 默认值",
            "Use workspace default",
        )
        self.fields["translation_display"].choices = _translation_display_choices(
            self.ui_language
        )
        self.fields["translator_option"].choices = [
            (
                "",
                _ui_text(
                    self.ui_language,
                    "使用 workspace 默认值",
                    "Use workspace default",
                ),
            )
        ] + get_all_agent_choices()
        self.fields["additional_prompt"].required = False
        self.fields["summary_detail"].required = False
        self.fields["name"].required = False

        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            self.fields["groups"].queryset = FeedGroup.objects.filter(
                workspace=instance.workspace
            ).order_by("name")
            if instance.translator_content_type_id and instance.translator_object_id:
                self.fields["translator_option"].initial = (
                    f"{instance.translator_content_type_id}:{instance.translator_object_id}"
                )

    def clean_groups(self):
        groups = self.cleaned_data.get("groups")
        instance = getattr(self, "instance", None)
        if instance and instance.workspace_id and groups:
            mismatched = [group for group in groups if group.workspace_id != instance.workspace_id]
            if mismatched:
                raise forms.ValidationError(
                    _("Selected groups must belong to the same workspace.")
                )
        return groups

    def save(self, commit=True):
        instance = super().save(commit=False)
        translator_value = self.cleaned_data.get("translator_option")
        if translator_value:
            content_type_id, object_id = map(int, translator_value.split(":"))
            instance.translator_content_type_id = content_type_id
            instance.translator_object_id = object_id
        else:
            instance.translator_content_type_id = None
            instance.translator_object_id = None

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class HubWorkspaceProviderForm(forms.Form):
    workspace = forms.ModelChoiceField(
        queryset=Workspace.objects.filter(is_active=True).order_by("name"),
        label=_("Workspace"),
    )
    default_target_language = forms.ChoiceField(
        choices=(),
        label=_("Default Feed Output Language"),
    )
    default_translator_option = forms.ChoiceField(
        choices=(),
        required=False,
        label=_("Default Translator"),
    )
    default_summarizer = forms.ModelChoiceField(
        queryset=OpenAIAgent.objects.filter(valid=True).order_by("name"),
        required=False,
        label=_("Default Summarizer"),
    )

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        workspace_queryset = kwargs.pop("workspace_queryset", None)
        super().__init__(*args, **kwargs)
        if workspace_queryset is not None:
            self.fields["workspace"].queryset = workspace_queryset.order_by("name")
        self.fields["default_target_language"].choices = list(
            Feed._meta.get_field("target_language").choices
        )
        self.fields["default_summarizer"].empty_label = _ui_text(
            self.ui_language,
            "不设置默认摘要器",
            "No default summarizer",
        )
        self.fields["default_translator_option"].choices = [
            (
                "",
                _ui_text(
                    self.ui_language,
                    "不设置默认翻译器",
                    "Use no default translator",
                ),
            )
        ] + get_all_agent_choices()

    def set_workspace_initial(self, workspace):
        self.initial["workspace"] = workspace.id
        self.initial["default_target_language"] = workspace.default_target_language
        self.initial["default_summarizer"] = workspace.default_summarizer_id
        if (
            workspace.default_translator_content_type_id
            and workspace.default_translator_object_id
        ):
            self.initial["default_translator_option"] = (
                f"{workspace.default_translator_content_type_id}:"
                f"{workspace.default_translator_object_id}"
            )
        else:
            self.initial["default_translator_option"] = ""

    def save(self):
        workspace = self.cleaned_data["workspace"]
        workspace.default_target_language = self.cleaned_data["default_target_language"]
        workspace.default_summarizer = self.cleaned_data["default_summarizer"]
        translator_value = self.cleaned_data.get("default_translator_option")
        if translator_value:
            content_type_id, object_id = map(int, translator_value.split(":"))
            workspace.default_translator_content_type_id = content_type_id
            workspace.default_translator_object_id = object_id
        else:
            workspace.default_translator_content_type_id = None
            workspace.default_translator_object_id = None
        workspace.save()
        return workspace


class HubBulkExportForm(forms.Form):
    EXPORT_VARIANT_CHOICES = [
        ("translated", _("Chinese / translated")),
        ("proxy", _("English / original")),
    ]
    EXPORT_FORMAT_CHOICES = [
        ("opml", _("OPML")),
        ("links", _("Feed links")),
    ]

    selected_feeds = forms.CharField(widget=forms.HiddenInput())
    export_variant = forms.ChoiceField(choices=EXPORT_VARIANT_CHOICES, initial="translated")
    export_format = forms.ChoiceField(choices=EXPORT_FORMAT_CHOICES, initial="opml")

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["export_variant"].choices = [
            (
                "translated",
                _ui_text(self.ui_language, "中文翻译版", "Chinese / translated"),
            ),
            (
                "proxy",
                _ui_text(self.ui_language, "英文原版", "English / original"),
            ),
        ]
        self.fields["export_format"].choices = [
            ("opml", "OPML"),
            (
                "links",
                _ui_text(self.ui_language, "订阅链接", "Feed links"),
            ),
        ]


class HubBulkEditForm(forms.Form):
    GROUP_MODE_CHOICES = [
        ("keep", _("Keep groups")),
        ("replace", _("Replace groups")),
        ("add", _("Add groups")),
        ("remove", _("Remove groups")),
    ]
    TAG_MODE_CHOICES = [
        ("keep", _("Keep tags")),
        ("replace", _("Replace tags")),
        ("add", _("Add tags")),
        ("remove", _("Remove tags")),
    ]
    PROVIDER_MODE_CHOICES = [
        ("keep", _("Keep provider settings")),
        ("workspace_default", _("Use workspace default provider")),
        ("override", _("Set explicit provider override")),
    ]
    RECORD_ACTION_CHOICES = [
        ("keep", _("Keep selected feeds")),
        ("archive", _("Archive selected feeds")),
        ("unarchive", _("Unarchive selected feeds")),
        ("delete", _("Delete selected feeds")),
    ]

    selected_feeds = forms.CharField(widget=forms.HiddenInput())
    group_mode = forms.ChoiceField(choices=GROUP_MODE_CHOICES, initial="keep")
    groups = forms.ModelMultipleChoiceField(
        queryset=FeedGroup.objects.select_related("workspace").order_by(
            "workspace__name", "name"
        ),
        required=False,
    )
    tag_mode = forms.ChoiceField(choices=TAG_MODE_CHOICES, initial="keep")
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all().order_by("name"),
        required=False,
    )
    provider_mode = forms.ChoiceField(choices=PROVIDER_MODE_CHOICES, initial="keep")
    translator_option = forms.ChoiceField(choices=(), required=False)
    summarizer = forms.ModelChoiceField(
        queryset=OpenAIAgent.objects.filter(valid=True).order_by("name"),
        required=False,
    )
    translation_display = forms.TypedChoiceField(
        choices=Feed.TRANSLATION_DISPLAY_CHOICES,
        coerce=int,
        required=False,
        empty_value=None,
    )
    record_action = forms.ChoiceField(choices=RECORD_ACTION_CHOICES, initial="keep")

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        workspace_queryset = kwargs.pop("workspace_queryset", None)
        tag_queryset = kwargs.pop("tag_queryset", None)
        super().__init__(*args, **kwargs)
        if workspace_queryset is not None:
            self.fields["groups"].queryset = FeedGroup.objects.select_related(
                "workspace"
            ).filter(workspace__in=workspace_queryset).order_by(
                "workspace__name", "name"
            )
        if tag_queryset is not None:
            self.fields["tags"].queryset = tag_queryset.order_by("name")
        self.fields["group_mode"].choices = [
            ("keep", _ui_text(self.ui_language, "保持 groups 不变", "Keep groups")),
            ("replace", _ui_text(self.ui_language, "替换 groups", "Replace groups")),
            ("add", _ui_text(self.ui_language, "追加 groups", "Add groups")),
            ("remove", _ui_text(self.ui_language, "移除 groups", "Remove groups")),
        ]
        self.fields["tag_mode"].choices = [
            ("keep", _ui_text(self.ui_language, "保持 tags 不变", "Keep tags")),
            ("replace", _ui_text(self.ui_language, "替换 tags", "Replace tags")),
            ("add", _ui_text(self.ui_language, "追加 tags", "Add tags")),
            ("remove", _ui_text(self.ui_language, "移除 tags", "Remove tags")),
        ]
        self.fields["provider_mode"].choices = [
            (
                "keep",
                _ui_text(
                    self.ui_language,
                    "保持 provider 设置",
                    "Keep provider settings",
                ),
            ),
            (
                "workspace_default",
                _ui_text(
                    self.ui_language,
                    "恢复为 workspace 默认 provider",
                    "Use workspace default provider",
                ),
            ),
            (
                "override",
                _ui_text(
                    self.ui_language,
                    "设置显式 provider 覆盖",
                    "Set explicit provider override",
                ),
            ),
        ]
        self.fields["record_action"].choices = [
            (
                "keep",
                _ui_text(
                    self.ui_language,
                    "保持所选 feeds",
                    "Keep selected feeds",
                ),
            ),
            (
                "archive",
                _ui_text(
                    self.ui_language,
                    "归档所选 feeds",
                    "Archive selected feeds",
                ),
            ),
            (
                "unarchive",
                _ui_text(
                    self.ui_language,
                    "取消归档所选 feeds",
                    "Unarchive selected feeds",
                ),
            ),
            (
                "delete",
                _ui_text(
                    self.ui_language,
                    "删除所选 feeds",
                    "Delete selected feeds",
                ),
            ),
        ]
        self.fields["summarizer"].empty_label = _ui_text(
            self.ui_language,
            "不覆盖摘要器",
            "No summarizer override",
        )
        self.fields["translation_display"].choices = _translation_display_choices(
            self.ui_language,
            include_blank=True,
        )
        self.fields["translator_option"].choices = [
            (
                "",
                _ui_text(
                    self.ui_language,
                    "不设置显式翻译器覆盖",
                    "No explicit translator override",
                ),
            )
        ] + get_all_agent_choices()


class HubUiPreferenceForm(forms.Form):
    UI_LANGUAGE_CHOICES = [
        ("zh-hans", _("Simplified Chinese")),
        ("en-us", _("English")),
    ]
    THEME_CHOICES = [
        ("system", _("Follow system")),
        ("light", _("Light")),
        ("dark", _("Dark")),
    ]

    ui_language = forms.ChoiceField(choices=UI_LANGUAGE_CHOICES)
    theme = forms.ChoiceField(choices=THEME_CHOICES)

    def __init__(self, *args, **kwargs):
        self.ui_language_value = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["ui_language"].choices = [
            (
                "zh-hans",
                _ui_text(
                    self.ui_language_value,
                    "简体中文",
                    "Chinese (Simplified)",
                ),
            ),
            ("en-us", "English"),
        ]
        self.fields["theme"].choices = [
            (
                "system",
                _ui_text(
                    self.ui_language_value,
                    "跟随系统",
                    "Follow system",
                ),
            ),
            ("light", _ui_text(self.ui_language_value, "浅色", "Light")),
            ("dark", _ui_text(self.ui_language_value, "深色", "Dark")),
        ]


class HubLoginForm(AuthenticationForm):
    username = forms.CharField(
        label=_("Username"),
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "用户名",
            "Username",
        )
        self.fields["password"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "密码",
            "Password",
        )


class HubPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "当前密码",
            "Current password",
        )
        self.fields["new_password1"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "新密码",
            "New password",
        )
        self.fields["new_password2"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "再次输入新密码",
            "Repeat new password",
        )


class HubUserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(choices=WorkspaceMembership.ROLE_CHOICES)
    password1 = forms.CharField(widget=forms.PasswordInput, label=_("Password"))
    password2 = forms.CharField(widget=forms.PasswordInput, label=_("Repeat Password"))

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        role_choices = kwargs.pop("role_choices", None)
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False
        self.fields["first_name"].required = False
        self.fields["last_name"].required = False
        if role_choices is not None:
            self.fields["role"].choices = role_choices
        self.fields["username"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "登录用户名",
            "Login username",
        )

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("The two password fields did not match."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class HubWorkspaceMemberRoleForm(forms.Form):
    role = forms.ChoiceField(choices=WorkspaceMembership.ROLE_CHOICES, label=_("Role"))

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        role_choices = kwargs.pop("role_choices", None)
        super().__init__(*args, **kwargs)
        if role_choices is not None:
            self.fields["role"].choices = role_choices
