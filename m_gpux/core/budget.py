"""Per-account monthly spending limits (``~/.m-gpux/budgets.json``).

A budget caps what m-gpux is willing to spend on an account in the current
calendar month, on top of the account's free monthly credit. The ``"*"`` key is
the default limit for accounts without their own entry.
"""

from __future__ import annotations

from typing import Optional

from m_gpux.core.state import STATE_DIR, _read_json, _write_json

BUDGETS_PATH = STATE_DIR / "budgets.json"
DEFAULT_KEY = "*"


def load_budgets() -> dict[str, float]:
    data = _read_json(BUDGETS_PATH, {})
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in data.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def set_budget(profile: Optional[str], limit: float) -> None:
    budgets = load_budgets()
    budgets[profile or DEFAULT_KEY] = float(limit)
    _write_json(BUDGETS_PATH, budgets)


def clear_budget(profile: Optional[str]) -> bool:
    budgets = load_budgets()
    key = profile or DEFAULT_KEY
    if key not in budgets:
        return False
    del budgets[key]
    _write_json(BUDGETS_PATH, budgets)
    return True


def budget_for(profile: str, budgets: Optional[dict[str, float]] = None) -> Optional[float]:
    budgets = load_budgets() if budgets is None else budgets
    return budgets.get(profile, budgets.get(DEFAULT_KEY))


def spendable(profile: str, used: float, monthly_credit: float,
              budgets: Optional[dict[str, float]] = None) -> float:
    """Dollars m-gpux may still spend on *profile* this month: the budget left
    when one is set (it may be above or below the free credit), otherwise the
    free credit left."""
    limit = budget_for(profile, budgets)
    cap = monthly_credit if limit is None else limit
    return max(cap - used, 0.0)
