"""
retry.py — Exponential backoff retry utilities for browser operations.
منطق إعادة المحاولة مع تراجع أسي لعمليات المتصفح

Provides a decorator and a helper function for retrying Playwright
operations that may fail transiently (network hiccups, slow SPA renders,
intermittent element-not-found errors).

Usage:
    @retry_with_backoff(max_attempts=3, initial_delay=2.0)
    def my_browser_op():
        ...

    # or imperatively:
    result = retry_browser_op(run_playwright_search, args..., task_id="t-123")
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, Type, TypeVar

log = logging.getLogger("fasah.browser.retry")

T = TypeVar("T")


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable:
    """
    Decorator: retry a function with exponential backoff on failure.

    مُزيّن: إعادة محاولة الدالة مع تراجع أسي عند الفشل.

    Args:
        max_attempts:   Total attempts including the first call.
        initial_delay:  Seconds to wait before the *first* retry.
        backoff_factor: Multiply the delay by this after each failure.
        max_delay:      Ceiling on the retry delay (seconds).
        exceptions:     Exception types to catch and retry. Others propagate immediately.
        on_retry:       Optional callback(attempt_number, exception) called before sleep.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        log.error(
                            "[retry] '%s' failed after %d attempt(s): %s",
                            func.__name__, max_attempts, exc,
                        )
                        raise

                    log.warning(
                        "[retry] '%s' attempt %d/%d failed: %s — retrying in %.1fs",
                        func.__name__, attempt, max_attempts, exc, delay,
                    )

                    if on_retry is not None:
                        try:
                            on_retry(attempt, exc)
                        except Exception:
                            pass  # never let the callback crash the retry loop

                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            # Should be unreachable, but satisfies the type checker
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


def retry_browser_op(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    initial_delay: float = 2.0,
    task_id: str = "unknown",
    **kwargs: Any,
) -> T:
    """
    Imperatively retry a browser operation with exponential backoff.

    إعادة محاولة عملية المتصفح بشكل إجرائي مع التراجع الأسي.

    Unlike the decorator form, this logs the *task_id* in every message so
    failures can be correlated in the audit log.

    Args:
        func:          Callable to invoke.
        *args:         Positional arguments forwarded to func.
        max_attempts:  Total attempts including the first call.
        initial_delay: Seconds to wait before the first retry.
        task_id:       Logged with every retry message for traceability.
        **kwargs:      Keyword arguments forwarded to func.
    """
    delay = initial_delay
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts:
                log.error(
                    "[retry][task=%s] '%s' failed after %d attempt(s): %s",
                    task_id, getattr(func, "__name__", str(func)), max_attempts, exc,
                )
                raise

            log.warning(
                "[retry][task=%s] '%s' attempt %d/%d failed: %s — retrying in %.1fs",
                task_id, getattr(func, "__name__", str(func)),
                attempt, max_attempts, exc, delay,
            )
            time.sleep(delay)
            delay = min(delay * 2.0, 30.0)

    assert last_exc is not None
    raise last_exc
