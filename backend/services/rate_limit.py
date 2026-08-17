"""Small in-process limiter used until Redis is introduced.

It deliberately protects expensive/public routes and returns 429.  Deployment
with multiple workers should replace this with a shared Redis implementation.
"""
from collections import defaultdict, deque
from time import monotonic
from fastapi import HTTPException, Request

_hits: dict[str, deque[float]] = defaultdict(deque)

def enforce(request: Request, bucket: str, limit: int, window_seconds: int = 60) -> None:
    client = request.client.host if request.client else "unknown"
    key = f"{bucket}:{client}"
    now = monotonic(); q = _hits[key]
    while q and q[0] <= now - window_seconds: q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Bạn thao tác quá nhanh. Vui lòng thử lại sau ít phút.")
    q.append(now)
