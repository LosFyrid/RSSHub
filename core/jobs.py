import logging

from django.apps import apps
from django.db import close_old_connections

from core.cache import cache_tag
from core.management.commands.feed_updater import update_multiple_feeds, update_single_feed
from core.tasks.generate_digests import DigestGenerator

logger = logging.getLogger(__name__)


def refresh_feed_job(feed_id: int):
    close_old_connections()
    try:
        Feed = apps.get_model("core", "Feed")
        feed = Feed.objects.filter(pk=feed_id).first()
        if feed is None:
            logger.warning("Skip refresh_feed_job because feed %s was not found", feed_id)
            return False
        update_multiple_feeds([feed])
        return True
    finally:
        close_old_connections()


def update_single_feed_job(feed_id: int):
    close_old_connections()
    try:
        Feed = apps.get_model("core", "Feed")
        feed = Feed.objects.filter(pk=feed_id).first()
        if feed is None:
            logger.warning(
                "Skip update_single_feed_job because feed %s was not found", feed_id
            )
            return False
        return update_single_feed(feed)
    finally:
        close_old_connections()


def generate_digest_job(digest_id: int, force: bool = False):
    close_old_connections()
    try:
        Digest = apps.get_model("core", "Digest")
        digest = Digest.objects.filter(pk=digest_id).first()
        if digest is None:
            logger.warning(
                "Skip generate_digest_job because digest %s was not found", digest_id
            )
            return {"success": False, "error": "Digest not found"}
        generator = DigestGenerator(digest)
        return generator.generate(force=force)
    finally:
        close_old_connections()


def cache_tag_job(tag_slug: str, feed_type: str, format: str):
    close_old_connections()
    try:
        return cache_tag(tag_slug, feed_type, format)
    finally:
        close_old_connections()
