from django import forms
from django.utils.translation import gettext_lazy as _

from core.models import Workspace
from utils.modelAdmin_utils import get_all_agent_choices


class WorkspaceProviderForm(forms.ModelForm):
    default_translator_option = forms.ChoiceField(
        choices=(),
        required=False,
        label=_("Default Translator"),
    )

    class Meta:
        model = Workspace
        fields = [
            "default_target_language",
            "default_summarizer",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_translator_option"].choices = [
            ("", _("Use no default translator"))
        ] + get_all_agent_choices()

        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            if (
                instance.default_translator_content_type_id
                and instance.default_translator_object_id
            ):
                self.fields["default_translator_option"].initial = (
                    f"{instance.default_translator_content_type_id}:"
                    f"{instance.default_translator_object_id}"
                )

    def save(self, commit=True):
        instance = super().save(commit=False)
        value = self.cleaned_data.get("default_translator_option")
        if value:
            content_type_id, object_id = map(int, value.split(":"))
            instance.default_translator_content_type_id = content_type_id
            instance.default_translator_object_id = object_id
        else:
            instance.default_translator_content_type_id = None
            instance.default_translator_object_id = None

        if commit:
            instance.save()
        return instance


class WorkspaceForm(forms.ModelForm):
    class Meta:
        model = Workspace
        fields = "__all__"
