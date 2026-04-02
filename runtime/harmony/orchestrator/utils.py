"""Shared utilities for pipeline modules."""

from __future__ import annotations


def make_response(
    step: str,
    prompt: str,
    expect: str,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    resp: dict[str, object] = {"step": step, "prompt": prompt, "expect": expect}
    if metadata:
        resp["metadata"] = metadata
    return resp
