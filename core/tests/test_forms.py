from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
import uuid

from core.forms.feed_form import FeedForm
from core.forms.hub_forms import (
    HubDeepLAgentForm,
    HubFeedCreateForm,
    HubFeedEditForm,
    HubLibreTranslateAgentForm,
    HubOpenAIAgentForm,
    HubWorkspaceProviderForm,
)
from core.models import Feed, Workspace, FeedGroup
from core.models.agent import OpenAIAgent


class FeedFormTest(TestCase):
    """Tests for FeedForm functionality."""

    def setUp(self):
        self.agent = OpenAIAgent.objects.create(
            name=f"Test Agent {uuid.uuid4()}", api_key="key", valid=True
        )
        self.workspace = Workspace.get_default()
        self.group = FeedGroup.objects.create(workspace=self.workspace, name="Karpathy")
        self.ct = ContentType.objects.get_for_model(OpenAIAgent)
        self.agent_value = f"{self.ct.id}:{self.agent.id}"

    def test_form_functionality(self):
        """Test form initial values and save processing."""
        # Test initial values for existing instance
        feed = Feed.objects.create(
            workspace=self.workspace,
            feed_url="https://example.com/rss.xml",
            update_frequency=15,
            translate_title=True,
            translate_content=False,
            summary=True,
            translator_content_type=self.ct,
            translator_object_id=self.agent.id,
            summarizer=self.agent,
        )

        form = FeedForm(instance=feed)
        assert form.fields["translator_option"].initial == self.agent_value
        # summary_engine_option 字段不存在，已删除
        assert form.fields["simple_update_frequency"].initial == 15
        assert form.fields["translate_title"].initial == True
        assert form.fields["translate_content"].initial == False
        assert form.fields["summary"].initial == True

        # Test save processes custom fields
        form_data = {
            "update_frequency": 60,
            "max_posts": 20,
            "translation_display": 0,
            "total_tokens": 0,
            "total_characters": 0,
            "feed_url": "https://another.com/rss.xml",
            "simple_update_frequency": 60,
            "translate_title": True,
            "translate_content": True,
            "summary": False,
            "translator_option": self.agent_value,
            # summary_engine_option 字段不存在，已删除
            "workspace": self.workspace.id,
            "groups": [self.group.id],
            "source_kind": Feed.STANDARD,
            "target_language": "English",
            "summarizer": self.agent.id,
        }

        form = FeedForm(data=form_data)
        assert form.is_valid(), form.errors
        saved_feed = form.save()

        assert saved_feed.update_frequency == 60
        assert saved_feed.translate_title is True
        assert saved_feed.translate_content is True
        assert saved_feed.summary is False
        assert saved_feed.translator_content_type_id == self.ct.id
        assert saved_feed.translator_object_id == self.agent.id
        assert saved_feed.summarizer_id == self.agent.id
        assert saved_feed.workspace_id == self.workspace.id
        assert self.group in saved_feed.groups.all()

    def test_hub_feed_create_form_defaults_to_translate(self):
        form = HubFeedCreateForm()
        self.assertNotIn("source_kind", form.fields)

        form = HubFeedCreateForm(
            data={
                "workspace": self.workspace.id,
                "feed_url": "https://example.com/new.xml",
                "name": "New Feed",
                "groups": [self.group.id],
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        feed = form.save()
        self.assertEqual(feed.source_kind, Feed.TRANSLATE)
        self.assertEqual(feed.target_language, self.workspace.default_target_language)
        self.assertTrue(feed.translate_title)
        self.assertTrue(feed.translate_content)

    def test_workspace_provider_form_saves_defaults(self):
        form = HubWorkspaceProviderForm(
            data={
                "workspace": self.workspace.id,
                "default_target_language": "English",
                "default_translator_option": self.agent_value,
                "default_summarizer": self.agent.id,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        workspace = form.save()
        self.assertEqual(workspace.default_target_language, "English")
        self.assertEqual(workspace.default_summarizer_id, self.agent.id)
        self.assertEqual(
            workspace.default_translator_content_type_id,
            self.ct.id,
        )
        self.assertEqual(workspace.default_translator_object_id, self.agent.id)

    def test_hub_feed_edit_form_uses_workspace_scoped_groups(self):
        other_workspace = Workspace.objects.create(name="Other Workspace")
        FeedGroup.objects.create(workspace=other_workspace, name="Elsewhere")
        feed = Feed.objects.create(
            workspace=self.workspace,
            feed_url="https://example.com/edit.xml",
        )
        form = HubFeedEditForm(instance=feed)
        group_names = list(form.fields["groups"].queryset.values_list("name", flat=True))
        self.assertEqual(group_names, ["Karpathy"])

    def test_console_provider_forms_minimal_payloads(self):
        openai_form = HubOpenAIAgentForm(
            data={
                "name": "Console OpenAI",
                "api_key": "sk-test",
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4.1-mini",
            }
        )
        self.assertTrue(openai_form.is_valid(), openai_form.errors)

        deepl_form = HubDeepLAgentForm(
            data={
                "name": "Console DeepL",
                "api_key": "deepl-key",
                "server_url": "",
                "proxy": "",
            }
        )
        self.assertTrue(deepl_form.is_valid(), deepl_form.errors)

        libre_form = HubLibreTranslateAgentForm(
            data={
                "name": "Console Libre",
                "api_key": "",
                "server_url": "https://libretranslate.example.com",
            }
        )
        self.assertTrue(libre_form.is_valid(), libre_form.errors)
