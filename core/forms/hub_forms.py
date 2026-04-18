from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import (
    Feed,
    FeedGroup,
    DeepLAgent,
    LibreTranslateAgent,
    OpenAIAgent,
    Tag,
    Workspace,
    WorkspaceInvitation,
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
        self.available_translator_choices = []
        self.available_summarizer_count = 0
        super().__init__(*args, **kwargs)
        if workspace_queryset is not None:
            self.fields["workspace"].queryset = workspace_queryset.order_by("name")
        self.fields["default_target_language"].choices = list(
            Feed._meta.get_field("target_language").choices
        )
        summarizers = OpenAIAgent.objects.filter(valid=True).order_by("name")
        self.available_summarizer_count = summarizers.count()
        self.fields["default_summarizer"].queryset = summarizers
        self.fields["default_summarizer"].empty_label = _ui_text(
            self.ui_language,
            "不设置默认摘要器",
            "No default summarizer",
        )
        self.available_translator_choices = get_all_agent_choices()
        self.fields["default_translator_option"].choices = [
            (
                "",
                _ui_text(
                    self.ui_language,
                    "不设置默认翻译器",
                    "Use no default translator",
                ),
            )
        ] + self.available_translator_choices

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


class HubOpenAIAgentForm(forms.ModelForm):
    class Meta:
        model = OpenAIAgent
        fields = ["name", "api_key", "base_url", "model"]
        widgets = {
            "api_key": forms.PasswordInput(render_value=False),
        }

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "例如：OpenAI 主翻译器",
            "For example: Primary OpenAI translator",
        )
        self.fields["api_key"].widget.attrs["placeholder"] = "sk-..."
        self.fields["base_url"].widget.attrs["placeholder"] = "https://api.openai.com/v1"
        self.fields["model"].widget.attrs["placeholder"] = "gpt-4.1-mini"


class HubDeepLAgentForm(forms.ModelForm):
    class Meta:
        model = DeepLAgent
        fields = ["name", "api_key", "server_url", "proxy"]
        widgets = {
            "api_key": forms.PasswordInput(render_value=False),
        }

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "例如：DeepL 翻译器",
            "For example: DeepL translator",
        )
        self.fields["api_key"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "DeepL API Key",
            "DeepL API key",
        )
        self.fields["server_url"].required = False
        self.fields["proxy"].required = False
        self.fields["server_url"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "可选：自托管 DeepL 兼容地址",
            "Optional: self-hosted DeepL-compatible endpoint",
        )
        self.fields["proxy"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "可选：代理 URL",
            "Optional: proxy URL",
        )


class HubLibreTranslateAgentForm(forms.ModelForm):
    class Meta:
        model = LibreTranslateAgent
        fields = ["name", "api_key", "server_url"]
        widgets = {
            "api_key": forms.PasswordInput(render_value=False),
        }

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "例如：LibreTranslate 备用翻译器",
            "For example: LibreTranslate fallback translator",
        )
        self.fields["api_key"].required = False
        self.fields["api_key"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "如果服务要求鉴权，则填写",
            "Fill only if the service requires auth",
        )
        self.fields["server_url"].widget.attrs["placeholder"] = (
            "https://libretranslate.example.com"
        )


class HubWorkspaceCreateForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = [
            "name",
            "description",
            "default_target_language",
        ]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "例如：AI 研究、Karpathy、BuilderPulse",
            "For example: AI Research, Karpathy, BuilderPulse",
        )
        self.fields["description"].required = False
        self.fields["description"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "可选说明：这个 workspace 用来管理什么",
            "Optional note: what this workspace is for",
        )

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError(_("Workspace name is required."))
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.is_active = True
        if commit:
            instance.save()
        return instance


class HubWorkspaceEditForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = [
            "name",
            "description",
        ]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "例如：AI 研究、Karpathy、BuilderPulse",
            "For example: AI Research, Karpathy, BuilderPulse",
        )
        self.fields["description"].required = False
        self.fields["description"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "这个 workspace 的协作边界或主题范围",
            "What collaboration boundary or topic this workspace covers",
        )

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError(_("Workspace name is required."))
        queryset = Workspace.objects.exclude(pk=self.instance.pk if self.instance else None)
        if queryset.filter(Q(name__iexact=name) | Q(slug__iexact=name.replace(" ", "-"))).exists():
            raise forms.ValidationError(_("A workspace with a similar name already exists."))
        return name


class HubRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label=_("Password"))
    password2 = forms.CharField(widget=forms.PasswordInput, label=_("Repeat Password"))

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["username"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "登录用户名",
            "Login username",
        )
        self.fields["email"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "用于接收 workspace 邀请的邮箱",
            "Email used to receive workspace invitations",
        )
        self.fields["first_name"].required = False
        self.fields["last_name"].required = False

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError(_("Email is required."))
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("A user with this email already exists."))
        return email

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError(_("Username is required."))
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("A user with this username already exists."))
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("The two password fields did not match."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = (user.email or "").strip().lower()
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


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
        user.email = (user.email or "").strip().lower()
        if commit:
            user.save()
        return user


class HubWorkspaceInviteForm(forms.ModelForm):
    role = forms.ChoiceField(choices=WorkspaceMembership.ROLE_CHOICES)

    class Meta:
        model = WorkspaceInvitation
        fields = ["email", "role", "note"]

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        role_choices = kwargs.pop("role_choices", None)
        super().__init__(*args, **kwargs)
        if role_choices is not None:
            self.fields["role"].choices = role_choices
        self.fields["email"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "输入对方注册时使用的邮箱",
            "Enter the email they use for sign-up",
        )
        self.fields["note"].required = False
        self.fields["note"].widget.attrs["placeholder"] = _ui_text(
            self.ui_language,
            "可选说明：为什么邀请他加入这个 workspace",
            "Optional note: why they are being invited to this workspace",
        )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError(_("Email is required."))
        return email

    def save(self, workspace, invited_by, commit=True):
        invitation = super().save(commit=False)
        invitation.workspace = workspace
        invitation.invited_by = invited_by
        if commit:
            invitation.save()
        return invitation


class HubInvitationDecisionForm(forms.Form):
    invitation_id = forms.IntegerField(widget=forms.HiddenInput())
    decision = forms.ChoiceField(
        choices=[
            ("accept", _("Accept")),
            ("decline", _("Decline")),
        ]
    )


class HubWorkspaceMemberRoleForm(forms.Form):
    role = forms.ChoiceField(choices=WorkspaceMembership.ROLE_CHOICES, label=_("Role"))

    def __init__(self, *args, **kwargs):
        self.ui_language = kwargs.pop("ui_language", "zh-hans")
        role_choices = kwargs.pop("role_choices", None)
        super().__init__(*args, **kwargs)
        if role_choices is not None:
            self.fields["role"].choices = role_choices
