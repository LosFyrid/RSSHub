from django import forms

from core.models import FeedGroup


class FeedGroupForm(forms.ModelForm):
    class Meta:
        model = FeedGroup
        fields = "__all__"
