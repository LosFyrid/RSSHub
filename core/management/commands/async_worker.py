from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the async background worker."

    def handle(self, *args, **options):
        if settings.ASYNC_TASK_BACKEND != "rq":
            raise CommandError(
                "ASYNC_TASK_BACKEND is not set to 'rq'; async worker is not enabled."
            )

        from redis import Redis
        from rq import Worker

        redis_conn = Redis.from_url(settings.ASYNC_REDIS_URL)
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting RQ worker for queue '{settings.ASYNC_QUEUE_NAME}'"
            )
        )
        worker = Worker([settings.ASYNC_QUEUE_NAME], connection=redis_conn)
        worker.work()
