"""Coordinate deletion with in-flight work, including aborted workers unwinding."""

from contextlib import contextmanager
from functools import wraps
from threading import RLock

from .errors import AppError

_lock = RLock()
_active: dict[str, int] = {}


def begin_novel_work(novel: str) -> None:
    with _lock:
        key = novel.strip()
        _active[key] = _active.get(key, 0) + 1


def end_novel_work(novel: str) -> None:
    with _lock:
        key = novel.strip()
        remaining = _active[key] - 1
        if remaining:
            _active[key] = remaining
        else:
            del _active[key]


def novel_work(function):
    @wraps(function)
    def wrapped(novel, *args, **kwargs):
        begin_novel_work(novel)
        try:
            return function(novel, *args, **kwargs)
        finally:
            end_novel_work(novel)
    return wrapped


@contextmanager
def novel_deletion(novel: str):
    # Keep new jobs from starting between the activity check and file removal.
    with _lock:
        if _active.get(novel.strip(), 0):
            raise AppError(
                "Translation is still active for this novel. Wait for it to finish "
                "or abort it and wait for the current request to stop before deleting.",
                409,
            )
        yield
