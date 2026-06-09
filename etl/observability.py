"""LangSmith tracing shim.

`@traceable` from langsmith if available; otherwise a no-op passthrough so the
ETL has no hard dependency on langsmith and runs fine with tracing disabled.
Tracing only actually emits when LANGSMITH_TRACING=true and LANGSMITH_API_KEY
are set in the environment (the langsmith SDK reads these).
"""

from __future__ import annotations

try:  # pragma: no cover - thin import guard
    from langsmith import traceable  # type: ignore
except Exception:  # langsmith not installed
    def traceable(*dargs, **dkwargs):  # type: ignore
        # Support both @traceable and @traceable(...) usage.
        if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
            return dargs[0]

        def _decorator(fn):
            return fn

        return _decorator


__all__ = ["traceable"]
