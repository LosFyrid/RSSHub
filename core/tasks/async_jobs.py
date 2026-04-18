import importlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings

from .task_manager import task_manager

logger = logging.getLogger(__name__)


def _import_string(path: str) -> Callable[..., Any]:
    module_path, attr_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def _resolve_callable(task_fn: Callable[..., Any] | str) -> tuple[Callable[..., Any], str]:
    if isinstance(task_fn, str):
        return _import_string(task_fn), task_fn
    return task_fn, f"{task_fn.__module__}.{task_fn.__qualname__}"


def execute_job_from_path(job_path: str, *args, **kwargs):
    task_fn = _import_string(job_path)
    return task_fn(*args, **kwargs)


@dataclass
class AsyncJobHandle:
    id: str
    backend: str
    raw: Any = None


class AsyncDispatcher:
    def submit_task(self, task_name: str, task_fn: Callable[..., Any] | str, *args, **kwargs):
        raise NotImplementedError


class LocalAsyncDispatcher(AsyncDispatcher):
    backend = "local"

    def submit_task(self, task_name: str, task_fn: Callable[..., Any] | str, *args, **kwargs):
        resolved, _ = _resolve_callable(task_fn)
        future = task_manager.submit_task(task_name, resolved, *args, **kwargs)
        return AsyncJobHandle(id=task_name, backend=self.backend, raw=future)


class RedisQueueDispatcher(AsyncDispatcher):
    backend = "rq"

    def __init__(self):
        from redis import Redis
        from rq import Queue

        self._queue_name = settings.ASYNC_QUEUE_NAME
        redis_conn = Redis.from_url(settings.ASYNC_REDIS_URL)
        self._queue = Queue(self._queue_name, connection=redis_conn)

    def submit_task(self, task_name: str, task_fn: Callable[..., Any] | str, *args, **kwargs):
        _, job_path = _resolve_callable(task_fn)
        job = self._queue.enqueue_call(
            func=execute_job_from_path,
            args=(job_path, *args),
            kwargs=kwargs,
            job_id=task_name,
        )
        return AsyncJobHandle(id=job.id, backend=self.backend, raw=job)


def get_async_dispatcher() -> AsyncDispatcher:
    mode = getattr(settings, "ASYNC_TASK_BACKEND", "local")
    if mode == "rq":
        return RedisQueueDispatcher()
    return LocalAsyncDispatcher()


def submit_async_task(task_name: str, task_fn: Callable[..., Any] | str, *args, **kwargs):
    dispatcher = get_async_dispatcher()
    logger.debug("Submitting async task %s via %s", task_name, dispatcher.backend)
    return dispatcher.submit_task(task_name, task_fn, *args, **kwargs)


def async_worker_enabled() -> bool:
    return getattr(settings, "ASYNC_TASK_BACKEND", "local") == "rq"


def cron_in_container_enabled() -> bool:
    return os.environ.get("ENABLE_CONTAINER_CRON", "0") == "1"
