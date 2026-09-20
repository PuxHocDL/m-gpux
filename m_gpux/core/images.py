"""Named (published) Modal Images built by ``m-gpux image build``.

Modal 1.5 lets an Image be published under a name (``Image.publish``) and
referenced later with ``Image.from_name`` without rebuilding. Names are scoped
to a workspace, so the local registry (``~/.m-gpux/images.json``) records which
profiles each image was published to.
"""

from __future__ import annotations

from typing import Any, Optional

from m_gpux.core.state import STATE_DIR, _read_json, _write_json, utc_now

IMAGES_PATH = STATE_DIR / "images.json"
DEBIAN_BASE_TEMPLATE = 'modal.Image.debian_slim(python_version="{python_version}")'


def list_images() -> dict[str, dict[str, Any]]:
    data = _read_json(IMAGES_PATH, {})
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def record_image(name: str, profile: str, **meta: Any) -> None:
    images = list_images()
    entry = images.get(name, {})
    profiles = sorted(set(entry.get("profiles", [])) | {profile})
    images[name] = {**entry, **meta, "profiles": profiles, "updated_at": utc_now()}
    _write_json(IMAGES_PATH, images)


def forget_image(name: str) -> bool:
    images = list_images()
    if name not in images:
        return False
    del images[name]
    _write_json(IMAGES_PATH, images)
    return True


def images_for_profile(profile: Optional[str], python_version: Optional[str] = None) -> list[str]:
    out = []
    for name, meta in sorted(list_images().items()):
        if profile and profile not in meta.get("profiles", []):
            continue
        if python_version and meta.get("python") and meta["python"] != python_version:
            continue
        out.append(name)
    return out


def pick_published_image(profile: Optional[str], python_version: Optional[str] = None) -> Optional[str]:
    """Offer the images published to *profile*; returns a name or ``None`` (build from scratch).

    Asks nothing when there are none, so flows without published images are unchanged.
    """
    names = images_for_profile(profile, python_version)
    if not names:
        return None
    from m_gpux.core.ui import arrow_select

    images = list_images()
    options = [("Build from scratch", "debian_slim + your packages (slower first start)")]
    for n in names:
        meta = images[n]
        options.append((n, f"published image · {meta.get('summary', '')}".rstrip(" ·")))
    idx = arrow_select(options, title="Base image", default=1)
    return None if idx == 0 else names[idx - 1]


def apply_base_image(template: str, image_name: Optional[str]) -> str:
    """Swap the debian_slim base of a generated-script template for a published image."""
    if not image_name:
        return template
    return template.replace(DEBIAN_BASE_TEMPLATE, f'modal.Image.from_name("{image_name}")')
