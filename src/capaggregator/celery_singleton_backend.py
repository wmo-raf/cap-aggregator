import threading

from celery_singleton.backends import RedisBackend
from celery_singleton.backends.base import BaseBackend
from django_redis import get_redis_connection


class RedisBackendForSingleton(RedisBackend):
    def __init__(self, *args, **kwargs):
        """Use the existing django-redis connection instead of creating a new one."""

        self.redis = get_redis_connection("default")

    def get(self, lock):
        # django-redis connections return bytes (no decode_responses, unlike the
        # library's own Redis.from_url) — decode so duplicate enqueues get a str
        # task id back in their AsyncResult
        value = self.redis.get(lock)
        return value.decode() if isinstance(value, bytes) else value


class LocMemBackendForSingleton(BaseBackend):
    """In-process singleton lock store for test runs, which swap the default
    cache to LocMem so nothing bleeds into the dev Redis (see settings.base)."""

    def __init__(self, *args, **kwargs):
        self._locks = {}
        self._mutex = threading.Lock()

    def lock(self, lock, task_id, expiry=None):
        with self._mutex:
            if lock in self._locks:
                return False
            self._locks[lock] = task_id
            return True

    def unlock(self, lock):
        with self._mutex:
            self._locks.pop(lock, None)

    def get(self, lock):
        with self._mutex:
            return self._locks.get(lock)

    def clear(self, key_prefix):
        with self._mutex:
            self._locks = {k: v for k, v in self._locks.items() if not k.startswith(key_prefix)}
