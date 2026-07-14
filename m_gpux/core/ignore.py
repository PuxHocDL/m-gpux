"""Exclude-pattern helpers for generated Modal scripts."""

from __future__ import annotations

from typing import Iterable

__all__ = ["to_recursive_ignore"]


def to_recursive_ignore(patterns: Iterable[str]) -> list[str]:
    """Make exclude patterns match at every depth, not just the repo root.

    ``Image.add_local_dir(ignore=[...])`` uses dockerignore-style matching,
    which anchors a bare name to the root: ``"node_modules"`` excludes
    ``./node_modules`` but **not** ``pkg/node_modules``. Left as-is, every
    nested ``node_modules`` / ``.venv`` / ``__pycache__`` gets uploaded into
    the workspace volume — in one real case 8,153 files / 144 MB, of which only
    ~213 files / 2 MB were actual work.

    Prefixing each name with a globstar makes it match at any depth (and it
    still matches at the root). A leading ``./`` and trailing ``/`` are
    stripped, but never leading dots — otherwise ``.venv`` would become
    ``venv``.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in patterns:
        p = raw.strip()
        while p.startswith("./"):
            p = p[2:]
        p = p.rstrip("/")
        if not p:
            continue
        pattern = p if p.startswith("**/") else f"**/{p}"
        if pattern not in seen:
            seen.add(pattern)
            out.append(pattern)
    return out
