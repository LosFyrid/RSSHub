from django.test import TestCase, RequestFactory, Client
from django.http import Http404, JsonResponse
from unittest.mock import patch, MagicMock
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.urls import reverse
from django.core.management import call_command
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth.models import User
import io
import json

from ..models import Feed, Tag, Workspace, FeedGroup, WorkspaceInvitation, WorkspaceMembership
from ..views import (
    rss,
    tag as tag_view,
    import_opml,
    workspace_feed,
    group_feed,
    hub_console,
    hub_login,
    hub_register,
    hub_dashboard,
    hub_create_workspace,
    hub_create_feed,
    hub_bulk_export,
    hub_bulk_edit,
    hub_set_preferences,
    hub_change_password,
    hub_update_feed,
    hub_update_workspace,
    hub_update_workspace_providers,
    hub_invite_workspace_member,
    hub_respond_invitation,
    hub_update_workspace_member,
    hub_remove_workspace_member,
)
from core.models.agent import OpenAIAgent


class ViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()
        self.workspace = Workspace.get_default()
        self.feed = Feed.objects.create(
            workspace=self.workspace,
            name="Test Feed",
            feed_url="https://example.com/rss.xml",
            slug="test-feed",
        )
        self.tag = Tag.objects.create(name="Test Tag", slug="test-tag")
        self.group = FeedGroup.objects.create(workspace=self.workspace, name="Karpathy")
        self.feed.groups.add(self.group)
        self.agent = OpenAIAgent.objects.create(
            name="Hub Agent", api_key="key", valid=True
        )
        self.user = User.objects.create_user("hub-user", password="password123")
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            role=WorkspaceMembership.OWNER,
        )

    def _create_opml_file(self, content, filename="test.opml"):
        """Helper method to create OPML file for testing."""
        return InMemoryUploadedFile(
            file=io.BytesIO(content.encode("utf-8")),
            field_name="opml_file",
            name=filename,
            content_type="application/xml",
            size=len(content),
            charset="utf-8",
        )

    def _setup_request_with_messages(self, request):
        """Helper method to setup request with messages."""
        setattr(request, "session", {})
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)
        return messages

    def _setup_hub_request(self, request):
        self._setup_request_with_messages(request)
        request.user = self.user
        return request

    @patch("core.views.cache")
    @patch("core.views.cache_rss")
    def test_rss_feed_view_found(self, mock_cache_rss, mock_cache):
        """Test the rss view when the feed is found."""
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_rss.return_value = (
            "<rss><channel><title>Test Feed</title></channel></rss>"
        )

        request = self.factory.get(f"/rss/{self.feed.slug}")
        response = rss(request, self.feed.slug)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        mock_cache_rss.assert_called_once_with(self.feed.slug, "t", "xml")

    def test_rss_feed_view_not_found(self):
        """Test the rss view when the feed is not found."""
        request = self.factory.get("/rss/non-existent-slug")
        response = rss(request, "non-existent-slug")
        self.assertEqual(response.status_code, 404)

    @patch("core.views.cache")
    @patch("core.views.cache_tag")
    def test_tag_view_found(self, mock_cache_tag, mock_cache):
        """Test the tag view when the tag is found."""
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_tag.return_value = (
            "<rss><channel><title>Tag Feed</title></channel></rss>"
        )

        request = self.factory.get(f"/tag/{self.tag.slug}")
        response = tag_view(request, self.tag.slug)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        mock_cache_tag.assert_called_once_with(self.tag.slug, "t", "xml")

    def test_tag_view_not_found(self):
        """Test the tag view when the tag is not found."""
        request = self.factory.get("/tag/non-existent-tag")
        response = tag_view(request, "non-existent-tag")
        self.assertEqual(response.status_code, 404)

    def test_import_opml_success(self):
        """Test the import_opml view with a valid OPML file."""
        opml_content = """
        <opml version="2.0">
            <body>
                <outline text="Feed 1" title="Feed 1" type="rss" xmlUrl="http://example.com/feed1.xml" />
            </body>
        </opml>
        """
        opml_file = self._create_opml_file(opml_content, "feeds.opml")
        request = self.factory.post(
            "/fake-url",
            {
                "opml_file": opml_file,
                "workspace": str(self.workspace.id),
                "create_groups_from_outlines": "on",
            },
        )
        messages = self._setup_request_with_messages(request)

        initial_feed_count = Feed.objects.count()
        response = import_opml(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:core_feed_changelist"))
        self.assertEqual(Feed.objects.count(), initial_feed_count + 1)
        self.assertTrue(
            Feed.objects.filter(feed_url="http://example.com/feed1.xml").exists()
        )
        self.assertIn("OPML file imported successfully.", [str(m) for m in messages])

    def test_import_opml_with_nested_categories(self):
        """Test importing an OPML file with nested categories."""
        opml_content = """
        <opml version="2.0">
            <body>
                <outline text="News">
                    <outline text="Tech News" title="Tech News" type="rss" xmlUrl="http://example.com/technews.xml" />
                </outline>
            </body>
        </opml>
        """
        opml_file = self._create_opml_file(opml_content, "nested.opml")
        request = self.factory.post(
            "/fake-url",
            {
                "opml_file": opml_file,
                "workspace": str(self.workspace.id),
                "create_groups_from_outlines": "on",
            },
        )
        self._setup_request_with_messages(request)

        import_opml(request)

        self.assertTrue(
            Feed.objects.filter(feed_url="http://example.com/technews.xml").exists()
        )
        new_feed = Feed.objects.get(feed_url="http://example.com/technews.xml")
        self.assertTrue(new_feed.tags.filter(name="News").exists())
        self.assertTrue(new_feed.groups.filter(name="News").exists())

    def test_import_opml_invalid_file(self):
        """Test importing an invalid OPML file (missing body)."""
        opml_content = "<opml version='2.0'><head></head></opml>"
        opml_file = self._create_opml_file(opml_content, "invalid.opml")
        request = self.factory.post(
            "/fake-url",
            {
                "opml_file": opml_file,
                "workspace": str(self.workspace.id),
            },
        )
        messages = self._setup_request_with_messages(request)

        initial_feed_count = Feed.objects.count()
        import_opml(request)

        self.assertEqual(Feed.objects.count(), initial_feed_count)
        self.assertIn("Invalid OPML: Missing body element", [str(m) for m in messages])

    @patch("core.views.feed2json")
    @patch("core.views.cache")
    @patch("core.views.cache_rss")
    def test_rss_view_json_format(self, mock_cache_rss, mock_cache, mock_feed2json):
        """Test the rss view with format='json'."""
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_rss.return_value = (
            "<rss><channel><title>Test Feed</title></channel></rss>"
        )
        mock_feed2json.return_value = {"title": "JSON Feed"}

        request = self.factory.get(f"/rss/{self.feed.slug}")
        response = rss(request, self.feed.slug, feed_type="o", format="json")

        mock_cache_rss.assert_called_once_with(self.feed.slug, "o", "json")
        mock_feed2json.assert_called_once_with(
            "<rss><channel><title>Test Feed</title></channel></rss>"
        )
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 200)
        json_content = json.loads(response.content)
        self.assertEqual(json_content["title"], "JSON Feed")

    @patch("core.views.feed2json")
    @patch("core.views.cache")
    @patch("core.views.cache_rss")
    def test_rss_view_json_format_no_feed_data(
        self, mock_cache_rss, mock_cache, mock_feed2json
    ):
        """Test the rss view with format='json' when no feed data is available."""
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_rss.return_value = None  # No feed data
        mock_feed2json.return_value = {"title": "JSON Feed"}

        request = self.factory.get(f"/rss/{self.feed.slug}")
        response = rss(request, self.feed.slug, format="json")

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(response.status_code, 404)
        json_content = json.loads(response.content)
        self.assertEqual(json_content["error"], "No feed data available")

    @patch("core.views.cache")
    @patch("core.views.cache_rss")
    def test_rss_view_xml_format_no_feed_data(self, mock_cache_rss, mock_cache):
        """Test the rss view with format='xml' when no feed data is available."""
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_rss.return_value = None  # No feed data

        request = self.factory.get(f"/rss/{self.feed.slug}")
        response = rss(request, self.feed.slug, format="xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml; charset=utf-8")
        # Check that error message is in the response content
        response_content = b"".join(response.streaming_content)
        self.assertIn(b"<error>No feed data available</error>", response_content)

    @patch("core.views.cache")
    @patch("core.views.cache_rss")
    def test_rss_view_cache_hit(self, mock_cache_rss, mock_cache):
        """Test the rss view when cache hit occurs."""
        cached_content = "<rss><channel><title>Cached Feed</title></channel></rss>"
        mock_cache.get.return_value = cached_content  # Cache hit
        mock_cache_rss.return_value = (
            "<rss><channel><title>Fresh Feed</title></channel></rss>"
        )

        request = self.factory.get(f"/rss/{self.feed.slug}")
        response = rss(request, self.feed.slug)

        self.assertEqual(response.status_code, 200)
        # Should not call cache_rss when cache hits
        mock_cache_rss.assert_not_called()
        # Check that cached content is returned
        response_content = b"".join(response.streaming_content)
        self.assertEqual(response_content, cached_content.encode())

    @patch("core.views.cache")
    @patch("core.views.cache_tag")
    def test_tag_view_cache_hit(self, mock_cache_tag, mock_cache):
        """Test the tag view when cache hit occurs."""
        cached_content = "<rss><channel><title>Cached Tag Feed</title></channel></rss>"
        mock_cache.get.return_value = cached_content  # Cache hit
        mock_cache_tag.return_value = (
            "<rss><channel><title>Fresh Tag Feed</title></channel></rss>"
        )

        request = self.factory.get(f"/tag/{self.tag.slug}")
        response = tag_view(request, self.tag.slug)

        self.assertEqual(response.status_code, 200)
        # Should not call cache_tag when cache hits
        mock_cache_tag.assert_not_called()
        # Check that cached content is returned
        response_content = b"".join(response.streaming_content)
        self.assertEqual(response_content, cached_content.encode())

    @patch("core.views.cache")
    @patch("core.views.cache_tag")
    def test_tag_view_exception_handling(self, mock_cache_tag, mock_cache):
        """Test the tag view when an exception occurs."""
        mock_cache.get.return_value = None  # Cache miss
        mock_cache_tag.side_effect = Exception("Cache tag error")

        request = self.factory.get(f"/tag/{self.tag.slug}")
        response = tag_view(request, self.tag.slug)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.content,
            b"Feed not found, Maybe it's still in progress, Please try again later.",
        )

    def test_import_opml_get_request(self):
        """Test the import_opml view with GET request."""
        request = self.factory.get("/fake-url")
        response = import_opml(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:core_feed_changelist"))

    def test_import_opml_no_file_uploaded(self):
        """Test the import_opml view when no file is uploaded."""
        request = self.factory.post("/fake-url", {})
        messages = self._setup_request_with_messages(request)

        response = import_opml(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("Please upload a valid OPML file.", [str(m) for m in messages])

    def test_import_opml_invalid_file_type(self):
        """Test the import_opml view with invalid file type."""
        # Create a mock file that's not InMemoryUploadedFile
        mock_file = MagicMock()
        mock_file.name = "test.txt"

        request = self.factory.post(
            "/fake-url",
            {"opml_file": mock_file, "workspace": str(self.workspace.id)},
        )
        messages = self._setup_request_with_messages(request)

        response = import_opml(request)

        self.assertEqual(response.status_code, 302)
        # The mock file will cause XML parsing error, so we check for that instead
        self.assertTrue(any("XML syntax error:" in str(m) for m in messages))

    def test_import_opml_xml_syntax_error(self):
        """Test the import_opml view with XML syntax error."""
        invalid_xml = "<opml version='2.0'><body><outline>"
        opml_file = self._create_opml_file(invalid_xml, "invalid.opml")
        request = self.factory.post(
            "/fake-url",
            {"opml_file": opml_file, "workspace": str(self.workspace.id)},
        )
        messages = self._setup_request_with_messages(request)

        initial_feed_count = Feed.objects.count()
        import_opml(request)

        self.assertEqual(Feed.objects.count(), initial_feed_count)
        self.assertTrue(any("XML syntax error:" in str(m) for m in messages))

    def test_import_opml_general_exception(self):
        """Test the import_opml view with general exception."""
        opml_content = """
        <opml version="2.0">
            <body>
                <outline text="Feed 1" title="Feed 1" type="rss" xmlUrl="http://example.com/feed1.xml" />
            </body>
        </opml>
        """
        opml_file = self._create_opml_file(opml_content, "feeds.opml")
        request = self.factory.post(
            "/fake-url",
            {"opml_file": opml_file, "workspace": str(self.workspace.id)},
        )
        messages = self._setup_request_with_messages(request)

        # Mock Feed.objects.get_or_create to raise an exception
        with patch("core.views.Feed.objects.get_or_create") as mock_get_or_create:
            mock_get_or_create.side_effect = Exception("Database error")

            initial_feed_count = Feed.objects.count()
            import_opml(request)

            self.assertEqual(Feed.objects.count(), initial_feed_count)
            self.assertTrue(
                any("Error importing OPML file:" in str(m) for m in messages)
            )

    def test_import_opml_with_tags(self):
        """Test importing an OPML file with tags."""
        opml_content = """
        <opml version="2.0">
            <body>
                <outline text="Technology">
                    <outline text="Tech Blog" title="Tech Blog" type="rss" xmlUrl="http://example.com/tech.xml" />
                </outline>
            </body>
        </opml>
        """
        opml_file = self._create_opml_file(opml_content, "with_tags.opml")
        request = self.factory.post(
            "/fake-url",
            {
                "opml_file": opml_file,
                "workspace": str(self.workspace.id),
                "create_groups_from_outlines": "on",
            },
        )
        self._setup_request_with_messages(request)

        initial_feed_count = Feed.objects.count()
        initial_tag_count = Tag.objects.count()

        import_opml(request)

        self.assertEqual(Feed.objects.count(), initial_feed_count + 1)
        self.assertEqual(Tag.objects.count(), initial_tag_count + 1)

        new_feed = Feed.objects.get(feed_url="http://example.com/tech.xml")
        new_tag = Tag.objects.get(name="Technology")
        self.assertTrue(new_feed.tags.filter(name="Technology").exists())

    @patch("core.views.cache")
    @patch("core.views.cache_workspace")
    def test_workspace_feed_found(self, mock_cache_workspace, mock_cache):
        mock_cache.get.return_value = None
        mock_cache_workspace.return_value = (
            "<rss><channel><title>Workspace Feed</title></channel></rss>"
        )

        request = self.factory.get(f"/rss/workspace/{self.workspace.slug}")
        response = workspace_feed(request, self.workspace.slug)

        self.assertEqual(response.status_code, 200)
        mock_cache_workspace.assert_called_once_with(self.workspace.slug, "t", "xml")

    @patch("core.views.cache")
    @patch("core.views.cache_group")
    def test_group_feed_found(self, mock_cache_group, mock_cache):
        mock_cache.get.return_value = None
        mock_cache_group.return_value = (
            "<rss><channel><title>Group Feed</title></channel></rss>"
        )

        request = self.factory.get(f"/rss/group/{self.workspace.slug}/{self.group.slug}")
        response = group_feed(request, self.workspace.slug, self.group.slug)

        self.assertEqual(response.status_code, 200)
        mock_cache_group.assert_called_once_with(
            self.workspace.slug, self.group.slug, "t", "xml"
        )

    def test_hub_dashboard_renders(self):
        request = self.factory.get("/?source_kind=translate")
        self._setup_hub_request(request)
        request.session["hub_theme"] = "dark"
        response = hub_dashboard(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"RSS Hub", response.content)
        self.assertIn("\u8ba2\u9605\u603b\u89c8".encode("utf-8"), response.content)
        self.assertIn(b'data-theme="dark"', response.content)
        self.assertIn(
            b'id="bulk-mode-panel" class="bulk-mode-panel is-hidden"',
            response.content,
        )

    def test_hub_dashboard_redirects_when_anonymous(self):
        request = self.factory.get("/")
        self._setup_request_with_messages(request)
        request.user = type("Anonymous", (), {"is_authenticated": False})()
        response = hub_dashboard(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/?next=%2F", response.url)

    def test_hub_login_renders(self):
        request = self.factory.get("/login/")
        self._setup_request_with_messages(request)
        request.user = type("Anonymous", (), {"is_authenticated": False})()
        response = hub_login(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("登录".encode("utf-8"), response.content)
        self.assertIn("创建账号".encode("utf-8"), response.content)

    def test_hub_register(self):
        response = self.client.post(
            reverse("hub:register"),
            {
                "username": "new-user",
                "email": "new-user@example.com",
                "first_name": "New",
                "last_name": "User",
                "password1": "new-user-pass",
                "password2": "new-user-pass",
            },
        )
        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username="new-user")
        self.assertEqual(created_user.email, "new-user@example.com")

    def test_hub_create_feed(self):
        request = self.factory.post(
            "/feeds/create/",
            {
                "workspace": self.workspace.id,
                "feed_url": "https://example.com/hub-created.xml",
                "name": "Hub Created",
                "groups": [self.group.id],
            },
        )
        self._setup_hub_request(request)
        response = hub_create_feed(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Feed.objects.filter(feed_url="https://example.com/hub-created.xml").exists())

    def test_hub_bulk_export_links(self):
        request = self.factory.post(
            "/feeds/bulk-export/",
            {
                "selected_feeds": str(self.feed.id),
                "export_variant": "proxy",
                "export_format": "links",
            },
        )
        self._setup_hub_request(request)
        response = hub_bulk_export(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn(f"/rss/proxy/{self.feed.slug}".encode(), response.content)

    def test_hub_bulk_export_opml(self):
        request = self.factory.post(
            "/feeds/bulk-export/",
            {
                "selected_feeds": str(self.feed.id),
                "export_variant": "translated",
                "export_format": "opml",
            },
        )
        self._setup_hub_request(request)
        response = hub_bulk_export(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        self.assertIn(b"/rss/test-feed", response.content)

    def test_hub_update_feed(self):
        request = self.factory.post(
            f"/feeds/{self.feed.id}/update/",
            {
                "name": "Renamed Feed",
                "groups": [self.group.id],
                "tags": [],
                "target_language": "English",
                "translate_title": "on",
                "translate_content": "on",
                "summary": "",
                "fetch_article": "",
                "max_posts": 20,
                "update_frequency": 30,
                "translation_display": 1,
                "translator_option": "",
                "summarizer": "",
                "summary_detail": "",
                "additional_prompt": "Keep product names in English",
                "is_archived": "on",
            },
        )
        self._setup_hub_request(request)
        response = hub_update_feed(request, self.feed.id)
        self.assertEqual(response.status_code, 302)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.name, "Renamed Feed")
        self.assertEqual(self.feed.translation_display, 1)
        self.assertTrue(self.feed.is_archived)

    def test_hub_bulk_edit_archives_feed(self):
        request = self.factory.post(
            "/feeds/bulk-edit/",
            {
                "selected_feeds": str(self.feed.id),
                "group_mode": "keep",
                "groups": [],
                "tag_mode": "keep",
                "tags": [],
                "provider_mode": "keep",
                "translator_option": "",
                "summarizer": "",
                "translation_display": "",
                "record_action": "archive",
            },
        )
        self._setup_hub_request(request)
        response = hub_bulk_edit(request)
        self.assertEqual(response.status_code, 302)
        self.feed.refresh_from_db()
        self.assertTrue(self.feed.is_archived)

    def test_hub_update_workspace_providers(self):
        from django.contrib.contenttypes.models import ContentType

        ct = ContentType.objects.get_for_model(OpenAIAgent)
        request = self.factory.post(
            "/workspaces/providers/",
            {
                "workspace": self.workspace.id,
                "default_target_language": "English",
                "default_translator_option": f"{ct.id}:{self.agent.id}",
                "default_summarizer": self.agent.id,
            },
        )
        self._setup_hub_request(request)
        response = hub_update_workspace_providers(request)
        self.assertEqual(response.status_code, 302)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.default_target_language, "English")
        self.assertEqual(self.workspace.default_summarizer_id, self.agent.id)

    def test_hub_set_preferences(self):
        request = self.factory.post(
            "/preferences/",
            {
                "ui_language": "en-us",
                "theme": "dark",
            },
        )
        self._setup_hub_request(request)
        response = hub_set_preferences(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(request.session["hub_ui_language"], "en-us")
        self.assertEqual(request.session["hub_theme"], "dark")

    def test_hub_change_password(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("hub:change_password"),
            {
                "old_password": "password123",
                "new_password1": "new-password-123",
                "new_password2": "new-password-123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-password-123"))

    def test_hub_create_workspace(self):
        request = self.factory.post(
            "/workspaces/create/",
            {
                "name": "New Workspace",
                "description": "A fresh space",
                "default_target_language": "English",
            },
        )
        self._setup_hub_request(request)
        response = hub_create_workspace(request)
        self.assertEqual(response.status_code, 302)
        workspace = Workspace.objects.get(name="New Workspace")
        self.assertEqual(workspace.default_target_language, "English")
        self.assertTrue(
            WorkspaceMembership.objects.filter(
                user=self.user,
                workspace=workspace,
                role=WorkspaceMembership.OWNER,
                is_active=True,
            ).exists()
        )

    def test_hub_dashboard_shows_workspace_create_entry_when_user_has_no_memberships(self):
        WorkspaceMembership.objects.filter(user=self.user).delete()
        request = self.factory.get("/")
        self._setup_hub_request(request)
        response = hub_dashboard(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("先去 Console 创建 workspace".encode("utf-8"), response.content)

    def test_hub_console_renders(self):
        request = self.factory.get("/console/")
        self._setup_hub_request(request)
        response = hub_console(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("用户控制台".encode("utf-8"), response.content)
        self.assertIn("Workspace 邀请".encode("utf-8"), response.content)

    def test_hub_update_workspace(self):
        request = self.factory.post(
            "/workspaces/update/",
            {
                "workspace_slug": self.workspace.slug,
                "name": "Updated Workspace",
                "description": "Updated description",
            },
        )
        self._setup_hub_request(request)
        response = hub_update_workspace(request)
        self.assertEqual(response.status_code, 302)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "Updated Workspace")

    def test_hub_invite_workspace_member(self):
        request = self.factory.post(
            "/workspaces/members/invite/",
            {
                "workspace_slug": self.workspace.slug,
                "email": "member-two@example.com",
                "role": WorkspaceMembership.VIEWER,
                "note": "Join the Karpathy workspace",
            },
        )
        self._setup_hub_request(request)
        response = hub_invite_workspace_member(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            WorkspaceInvitation.objects.filter(
                email="member-two@example.com",
                workspace=self.workspace,
                role=WorkspaceMembership.VIEWER,
                status=WorkspaceInvitation.PENDING,
            ).exists()
        )

    def test_hub_accept_invitation(self):
        invited_user = User.objects.create_user(
            "member-two",
            email="member-two@example.com",
            password="member-two-pass",
        )
        invitation = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            email="member-two@example.com",
            role=WorkspaceMembership.MANAGER,
            invited_by=self.user,
        )
        request = self.factory.post(
            f"/inbox/invitations/{invitation.id}/respond/",
            {"decision": "accept"},
        )
        self._setup_request_with_messages(request)
        request.user = invited_user
        response = hub_respond_invitation(request, invitation.id)
        self.assertEqual(response.status_code, 302)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, WorkspaceInvitation.ACCEPTED)
        self.assertTrue(
            WorkspaceMembership.objects.filter(
                user=invited_user,
                workspace=self.workspace,
                role=WorkspaceMembership.MANAGER,
                is_active=True,
            ).exists()
        )

    def test_hub_dashboard_workspace_switcher_only_shows_accessible_workspaces(self):
        other_workspace = Workspace.objects.create(name="Other Workspace")
        request = self.factory.get("/?workspace=other-workspace")
        self._setup_hub_request(request)
        response = hub_dashboard(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.workspace.name.encode("utf-8"), response.content)
        self.assertNotIn(other_workspace.name.encode("utf-8"), response.content)
        self.assertIn("当前 Workspace".encode("utf-8"), response.content)

    def test_owner_console_invite_form_includes_owner_role(self):
        request = self.factory.get("/console/")
        self._setup_hub_request(request)
        response = hub_console(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<option value="owner">Owner</option>', response.content)

    def test_manager_console_invite_form_excludes_owner_role(self):
        membership = self.user.workspace_memberships.get(workspace=self.workspace)
        membership.role = WorkspaceMembership.MANAGER
        membership.save(update_fields=["role", "updated_at"])
        request = self.factory.get("/console/")
        self._setup_hub_request(request)
        response = hub_console(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'<option value="owner">Owner</option>', response.content)

    def test_hub_update_workspace_member_role(self):
        member = User.objects.create_user("member-edit", password="password123")
        membership = WorkspaceMembership.objects.create(
            user=member,
            workspace=self.workspace,
            role=WorkspaceMembership.VIEWER,
        )
        request = self.factory.post(
            f"/workspaces/members/{membership.id}/role/",
            {"role": WorkspaceMembership.MANAGER},
        )
        self._setup_hub_request(request)
        response = hub_update_workspace_member(request, membership.id)
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.role, WorkspaceMembership.MANAGER)

    def test_hub_remove_workspace_member(self):
        member = User.objects.create_user("member-remove", password="password123")
        membership = WorkspaceMembership.objects.create(
            user=member,
            workspace=self.workspace,
            role=WorkspaceMembership.VIEWER,
        )
        request = self.factory.post(f"/workspaces/members/{membership.id}/remove/")
        self._setup_hub_request(request)
        response = hub_remove_workspace_member(request, membership.id)
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)

    def test_hub_prevents_removing_last_owner(self):
        request = self.factory.post(
            f"/workspaces/members/{self.user.workspace_memberships.get(workspace=self.workspace).id}/remove/"
        )
        self._setup_hub_request(request)
        response = hub_remove_workspace_member(
            request,
            self.user.workspace_memberships.get(workspace=self.workspace).id,
        )
        self.assertEqual(response.status_code, 302)
        membership = self.user.workspace_memberships.get(workspace=self.workspace)
        self.assertTrue(membership.is_active)

    def test_manager_can_manage_non_owner_members(self):
        owner_membership = self.user.workspace_memberships.get(workspace=self.workspace)
        owner_membership.role = WorkspaceMembership.MANAGER
        owner_membership.save(update_fields=["role", "updated_at"])
        member = User.objects.create_user("member-no-manage", password="password123")
        membership = WorkspaceMembership.objects.create(
            user=member,
            workspace=self.workspace,
            role=WorkspaceMembership.VIEWER,
        )
        request = self.factory.post(
            f"/workspaces/members/{membership.id}/role/",
            {"role": WorkspaceMembership.MANAGER},
        )
        self._setup_hub_request(request)
        response = hub_update_workspace_member(request, membership.id)
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.role, WorkspaceMembership.MANAGER)

    def test_manager_cannot_manage_owner_member(self):
        owner_membership = self.user.workspace_memberships.get(workspace=self.workspace)
        owner_membership.role = WorkspaceMembership.MANAGER
        owner_membership.save(update_fields=["role", "updated_at"])
        target_owner = User.objects.create_user("owner-two", password="password123")
        target_membership = WorkspaceMembership.objects.create(
            user=target_owner,
            workspace=self.workspace,
            role=WorkspaceMembership.OWNER,
        )
        request = self.factory.post(
            f"/workspaces/members/{target_membership.id}/role/",
            {"role": WorkspaceMembership.VIEWER},
        )
        self._setup_hub_request(request)
        response = hub_update_workspace_member(request, target_membership.id)
        self.assertEqual(response.status_code, 302)
        target_membership.refresh_from_db()
        self.assertEqual(target_membership.role, WorkspaceMembership.OWNER)


class DigestGeneratorCommandTestCase(TestCase):
    def setUp(self):
        self.agent = OpenAIAgent.objects.create(
            name="Digest Agent",
            api_key="key",
            valid=True,
        )

    @patch("core.management.commands.digest_generator.DigestGenerator")
    def test_digest_generator_filters_publish_days_without_backend_specific_sql(self, mock_generator):
        from core.models import Digest

        saturday_digest = Digest.objects.create(
            name="Saturday Digest",
            summarizer=self.agent,
            publish_days=["saturday"],
            is_active=True,
        )
        Digest.objects.create(
            name="Sunday Digest",
            summarizer=self.agent,
            publish_days=["sunday"],
            is_active=True,
        )
        mock_generator.return_value.generate.return_value = {
            "success": True,
            "articles_processed": 0,
        }

        call_command("digest_generator", "--publish-days", "saturday")

        mock_generator.assert_called_once_with(saturday_digest)
