"""Pick where to run a script: Kaggle, Colab or one of the Modal accounts.

:func:`plan` is pure: it takes what each platform reported (Kaggle quota and
free slots, Colab compute units, Modal spendable credit) and returns every
candidate with whether it can take the job and why, best first. Only accounts
the user configured are considered; respect each platform's terms (Kaggle, for
example, allows one account per person).
"""

from __future__ import annotations

from typing import Any, Optional

KAGGLE_SHAPES = {"T4": "NvidiaTeslaT4", "P100": "NvidiaTeslaP100"}
PLATFORMS = ("kaggle", "colab", "modal")


def _candidate(
    platform: str, account: str, gpu: str, ok: bool, note: str, score: float = 0.0, cost: Optional[float] = None
):
    return {"platform": platform, "account": account, "gpu": gpu, "ok": ok, "note": note, "score": score, "cost": cost}


def kaggle_candidates(rows: list[dict[str, Any]], gpu: Optional[str], hours: float) -> list[dict[str, Any]]:
    from m_gpux.core.kaggle import GPU_SLOTS

    out = []
    label = gpu or "P100"
    for row in rows:
        name = str(row.get("name"))
        if gpu and gpu not in KAGGLE_SHAPES:
            out.append(_candidate("kaggle", name, label, False, f"Kaggle offers {', '.join(KAGGLE_SHAPES)} only"))
            continue
        if row.get("error"):
            out.append(_candidate("kaggle", name, label, False, str(row["error"])[:80]))
            continue
        left = float(((row.get("quota") or {}).get("gpu") or {}).get("remaining") or 0)
        live = len(row.get("live") or [])
        if live >= GPU_SLOTS:
            out.append(_candidate("kaggle", name, label, False, f"both GPU slots busy ({live} running)"))
        elif left < hours:
            out.append(_candidate("kaggle", name, label, False, f"{left:.1f} h GPU left this week (< {hours:g} h)"))
        else:
            out.append(
                _candidate("kaggle", name, label, True, f"{left:.1f} h GPU left this week · free", score=left, cost=0.0)
            )
    return out


def colab_candidates(rows: list[dict[str, Any]], gpu: Optional[str], hours: float) -> list[dict[str, Any]]:
    from m_gpux.core.colab import GPUS

    out = []
    label = gpu or "T4"
    for row in rows:
        name = str(row.get("name"))
        if label not in GPUS:
            out.append(_candidate("colab", name, label, False, f"Colab offers {', '.join(GPUS)}"))
            continue
        if not row.get("logged_in"):
            out.append(_candidate("colab", name, label, False, "not logged in (m-gpux colab login)"))
            continue
        if row.get("error") or not row.get("usage"):
            out.append(_candidate("colab", name, label, False, str(row.get("error") or "no usage info")[:80]))
            continue
        balance = float(row["usage"].get("balance") or 0)
        if balance <= 0 and label != "T4":
            out.append(_candidate("colab", name, label, False, f"no compute units for {label}"))
            continue
        note = f"{balance:.1f} compute units" if balance > 0 else "free tier T4"
        out.append(_candidate("colab", name, label, True, note, score=balance))
    return out


def modal_candidates(
    balances: list[tuple[str, float, float]], gpu: Optional[str], hours: float
) -> list[dict[str, Any]]:
    from m_gpux.core.pricing import gpu_hourly

    label = gpu or "T4"
    hourly = gpu_hourly(label)
    cost = hourly * hours if hourly is not None else None
    out = []
    for profile, used, spendable in balances:
        if used < 0:
            out.append(_candidate("modal", profile, label, False, "billing unavailable"))
        elif cost is not None and spendable < cost:
            out.append(_candidate("modal", profile, label, False, f"${spendable:.2f} left < ~${cost:.2f} needed"))
        else:
            note = f"${spendable:.2f} left" + (f" · ~${cost:.2f} for {hours:g} h" if cost is not None else "")
            out.append(_candidate("modal", profile, label, True, note, score=spendable, cost=cost))
    return out


def plan(
    gpu: Optional[str],
    hours: float,
    *,
    where: str = "auto",
    kaggle_rows: Optional[list[dict[str, Any]]] = None,
    colab_rows: Optional[list[dict[str, Any]]] = None,
    modal_balances: Optional[list[tuple[str, float, float]]] = None,
) -> list[dict[str, Any]]:
    """Every candidate, usable ones first: free Kaggle quota, then Colab, then Modal credit."""
    order = PLATFORMS if where == "auto" else (where,)
    found: list[dict[str, Any]] = []
    for platform in order:
        if platform == "kaggle" and kaggle_rows is not None:
            found += sorted(kaggle_candidates(kaggle_rows, gpu, hours), key=lambda c: -c["score"])
        elif platform == "colab" and colab_rows is not None:
            found += sorted(colab_candidates(colab_rows, gpu, hours), key=lambda c: -c["score"])
        elif platform == "modal" and modal_balances is not None:
            found += sorted(modal_candidates(modal_balances, gpu, hours), key=lambda c: -c["score"])
    # Stable sort keeps platform priority among the usable ones.
    return sorted(found, key=lambda c: not c["ok"])


def kaggle_metadata(owner: str, slug: str, code_file: str, gpu: Optional[str]) -> dict[str, Any]:
    return {
        "id": f"{owner}/{slug}",
        "title": slug,
        "code_file": code_file,
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": KAGGLE_SHAPES.get(gpu or "", ""),
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
