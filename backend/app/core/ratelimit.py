"""Counting failed logins in Redis to slow down password guessing."""

from typing import cast

from redis import Redis


class LoginRateLimiter:
    def __init__(self, redis: Redis, max_failures: int, window_seconds: int) -> None:
        self._redis = redis
        self._max_failures = max_failures
        self._window_seconds = window_seconds

    @staticmethod
    def _keys(email: str, ip_address: str) -> list[str]:
        # Limit per e-mail (guessing one account from many places) and per
        # address (trying many accounts from one place).
        return [f"login-failures:email:{email.lower()}", f"login-failures:ip:{ip_address}"]

    def is_blocked(self, email: str, ip_address: str) -> bool:
        counts = cast(list[bytes | None], self._redis.mget(self._keys(email, ip_address)))
        return any(int(count or 0) >= self._max_failures for count in counts)

    def record_failure(self, email: str, ip_address: str) -> None:
        pipe = self._redis.pipeline()
        for key in self._keys(email, ip_address):
            pipe.incr(key)
            pipe.expire(key, self._window_seconds, nx=True)
        pipe.execute()

    def reset(self, email: str, ip_address: str) -> None:
        self._redis.delete(*self._keys(email, ip_address))
