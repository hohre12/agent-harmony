"""Shared utilities for pipeline modules."""

from __future__ import annotations


def make_response(
    step: str,
    prompt: str,
    expect: str,
    metadata: dict | None = None,
) -> dict:
    """Build a standardized response dict."""
    resp = {"step": step, "prompt": prompt, "expect": expect}
    if metadata:
        resp["metadata"] = metadata
    return resp
