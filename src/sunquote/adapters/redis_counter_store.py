"""The Redis implementation of the domain's `CounterStore` port."""

from redis.asyncio import Redis


class RedisCounterStore:
    """Counters as Redis integers that expire on their own.

    `INCR` and `EXPIRE ... NX` run in one transaction: the first increment sets the expiry,
    later ones leave it alone, and a crash cannot leave a counter that never expires.
    Redis errors propagate; the caller decides what a failing store means.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def increment(self, key: str, *, ttl_seconds: int) -> int:
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, ttl_seconds, nx=True)
            results = await pipeline.execute()
        return int(results[0])
