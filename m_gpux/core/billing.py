"""Billing access that works across Modal SDK versions.

Modal 1.5.1 replaced ``modal.billing.workspace_billing_report`` (now deprecated)
with ``modal.Workspace.billing.report()``, which also breaks each row's cost down
by resource (CPU, memory, each GPU type). 1.5.3 added ``billing.summary()`` for
metered vs. billed cost per billing cycle. We use the new API when the installed
SDK has it and fall back to the old function otherwise.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _client(token_id: str, token_secret: str):
    from modal.client import Client

    return Client.from_credentials(str(token_id), str(token_secret))


def _workspace(client):
    import modal

    workspace_cls = getattr(modal, "Workspace", None)
    if workspace_cls is None or not hasattr(workspace_cls, "from_context"):
        return None
    return workspace_cls.from_context(client=client)


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def billing_report(
    token_id: str,
    token_secret: str,
    start: datetime,
    end: Optional[datetime] = None,
    resolution: str = "d",
) -> list[dict[str, Any]]:
    """Return report rows as plain dicts.

    Each row has ``environment_name``, ``description``, ``interval_start``,
    ``cost`` (float) and ``cost_by_resource`` (``{resource: float}``; empty on
    SDKs older than 1.5.1).
    """
    client = _client(token_id, token_secret)
    workspace = _workspace(client)
    if workspace is not None:
        items = workspace.billing.report(start=start, end=end, resolution=resolution)
    else:
        from modal.billing import workspace_billing_report

        items = workspace_billing_report(start=start, end=end, resolution=resolution, client=client)

    rows = []
    for item in items:
        by_resource = _field(item, "cost_by_resource") or {}
        rows.append(
            {
                "environment_name": _field(item, "environment_name", "") or "",
                "description": _field(item, "description", "") or "",
                "interval_start": _field(item, "interval_start"),
                "cost": float(_field(item, "cost", 0) or 0),
                "cost_by_resource": {str(k): float(v) for k, v in dict(by_resource).items()},
            }
        )
    return rows


def billing_summary(token_id: str, token_secret: str) -> Optional[dict[str, Any]]:
    """Return this billing cycle's summary, or ``None`` if the SDK predates 1.5.3.

    Keys: ``metered_cost`` (usage before credits), ``billed_cost`` (what is
    invoiced), ``adjustments`` and ``metered_cost_breakdown`` (both
    ``{name: float}``).
    """
    workspace = _workspace(_client(token_id, token_secret))
    if workspace is None or not hasattr(workspace.billing, "summary"):
        return None
    summary = workspace.billing.summary()
    return {
        "metered_cost": float(summary.metered_cost),
        "billed_cost": float(summary.billed_cost),
        "adjustments": {str(k): float(v) for k, v in summary.adjustments.items()},
        "metered_cost_breakdown": {str(k): float(v) for k, v in summary.metered_cost_breakdown.items()},
    }


def month_usage(token_id: str, token_secret: str) -> float:
    """Return the current calendar month's metered cost in USD, or ``-1.0`` on failure."""
    try:
        summary = billing_summary(token_id, token_secret)
        if summary is not None:
            return summary["metered_cost"]
    except Exception:
        pass
    try:
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return sum(r["cost"] for r in billing_report(token_id, token_secret, month_start))
    except Exception:
        return -1.0
