from urllib.parse import parse_qsl, unquote, urlparse
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from core.tasks.async_jobs import (
    LocalAsyncDispatcher,
    RedisQueueDispatcher,
    execute_job_from_path,
    get_async_dispatcher,
    submit_async_task,
)


class RuntimeSettingsTest(SimpleTestCase):
    def test_postgres_database_url_shape_is_supported(self):
        parsed = urlparse(
            "postgresql://rsshub:secret@postgres:5432/rsshub?sslmode=require&connect_timeout=9"
        )
        query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        self.assertEqual(parsed.scheme, "postgresql")
        self.assertEqual(unquote(parsed.path.lstrip("/")), "rsshub")
        self.assertEqual(unquote(parsed.username or ""), "rsshub")
        self.assertEqual(unquote(parsed.password or ""), "secret")
        self.assertEqual(parsed.hostname, "postgres")
        self.assertEqual(parsed.port, 5432)
        self.assertEqual(query_params["sslmode"], "require")
        self.assertEqual(query_params["connect_timeout"], "9")


class AsyncDispatcherTest(SimpleTestCase):
    def test_execute_job_from_path(self):
        with patch("core.jobs.refresh_feed_job", return_value=True) as mock_job:
            result = execute_job_from_path("core.jobs.refresh_feed_job", 42)

        self.assertTrue(result)
        mock_job.assert_called_once_with(42)

    @override_settings(ASYNC_TASK_BACKEND="local")
    @patch("core.tasks.async_jobs.task_manager.submit_task")
    def test_submit_async_task_uses_local_dispatcher(self, mock_submit_task):
        mock_future = MagicMock()
        mock_submit_task.return_value = mock_future

        handle = submit_async_task(
            "refresh_feed_42",
            "core.jobs.refresh_feed_job",
            42,
        )

        self.assertEqual(handle.id, "refresh_feed_42")
        self.assertEqual(handle.backend, "local")
        mock_submit_task.assert_called_once()
        submit_args = mock_submit_task.call_args[0]
        self.assertEqual(submit_args[0], "refresh_feed_42")
        self.assertEqual(submit_args[1].__name__, "refresh_feed_job")
        self.assertEqual(submit_args[2], 42)

    @override_settings(
        ASYNC_TASK_BACKEND="rq",
        ASYNC_QUEUE_NAME="rsshub-default",
        ASYNC_REDIS_URL="redis://localhost:6379/1",
    )
    @patch("rq.Queue")
    @patch("redis.Redis")
    def test_submit_async_task_uses_rq_dispatcher(self, mock_redis, mock_queue_cls):
        mock_queue = MagicMock()
        mock_job = MagicMock(id="job-1")
        mock_queue.enqueue_call.return_value = mock_job
        mock_queue_cls.return_value = mock_queue

        handle = submit_async_task(
            "refresh_feed_42",
            "core.jobs.refresh_feed_job",
            42,
        )

        self.assertEqual(handle.id, "job-1")
        self.assertEqual(handle.backend, "rq")
        mock_redis.from_url.assert_called_once_with("redis://localhost:6379/1")
        mock_queue.enqueue_call.assert_called_once_with(
            func=execute_job_from_path,
            args=("core.jobs.refresh_feed_job", 42),
            kwargs={},
            job_id="refresh_feed_42",
        )

    @override_settings(ASYNC_TASK_BACKEND="local")
    def test_get_async_dispatcher_local(self):
        dispatcher = get_async_dispatcher()
        self.assertIsInstance(dispatcher, LocalAsyncDispatcher)

    @override_settings(
        ASYNC_TASK_BACKEND="rq",
        ASYNC_QUEUE_NAME="rsshub-default",
        ASYNC_REDIS_URL="redis://localhost:6379/1",
    )
    @patch("rq.Queue")
    @patch("redis.Redis")
    def test_get_async_dispatcher_rq(self, mock_redis, mock_queue_cls):
        dispatcher = get_async_dispatcher()
        self.assertIsInstance(dispatcher, RedisQueueDispatcher)
        mock_redis.from_url.assert_called_once_with("redis://localhost:6379/1")
        mock_queue_cls.assert_called_once()


class AsyncWorkerCommandTest(SimpleTestCase):
    @override_settings(ASYNC_TASK_BACKEND="local")
    def test_async_worker_requires_rq_backend(self):
        with self.assertRaises(CommandError):
            call_command("async_worker")

    @override_settings(
        ASYNC_TASK_BACKEND="rq",
        ASYNC_QUEUE_NAME="rsshub-default",
        ASYNC_REDIS_URL="redis://localhost:6379/1",
    )
    @patch("rq.Worker")
    @patch("redis.Redis")
    def test_async_worker_starts_worker(self, mock_redis, mock_worker_cls):
        worker = MagicMock()
        mock_worker_cls.return_value = worker

        call_command("async_worker")

        mock_redis.from_url.assert_called_once_with("redis://localhost:6379/1")
        mock_worker_cls.assert_called_once_with(
            ["rsshub-default"],
            connection=mock_redis.from_url.return_value,
        )
        worker.work.assert_called_once_with()
