"""m_gpux core framework.

This subpackage hosts the *Plugin / Provider* architecture used by m-gpux:

* :class:`PluginBase` — base class that every plugin (built-in or 3rd party)
  must subclass.
* :class:`PluginRegistry` — registry where plugins are collected.
* :func:`discover_plugins` — discovers built-in plugins and any plugin shipped
  via the ``m_gpux.plugins`` Python entry-point group.

It also re-exports the shared utilities used across plugins so that plugins
only need to ``from m_gpux.core import ...`` rather than reaching into other
plugin modules. This is what keeps the architecture *extensible*: a 3rd-party
plugin only depends on the core surface.
"""

from m_gpux.core.console import console
from m_gpux.core.gpus import AVAILABLE_GPUS, AVAILABLE_CPUS
from m_gpux.core.metrics import FUNCTIONS as METRICS_FUNCTIONS
from m_gpux.core.plugin import PluginBase, PluginRegistry, discover_plugins
from m_gpux.core.profiles import (
    MODAL_CONFIG_PATH,
    MONTHLY_CREDIT,
    activate_profile,
    get_all_balances,
    get_all_profiles,
    get_best_profile,
    load_config,
    load_profiles,
    save_config,
    select_profile,
    # Backwards-compatible aliases used inside plugin bodies.
    activate_profile as _activate_profile,
    load_profiles as _load_profiles,
    select_profile as _select_profile,
)
from m_gpux.core.runner import execute_modal_temp_script, scan_apps_across_profiles
from m_gpux.core.ui import arrow_select

__all__ = [
    "PluginBase",
    "PluginRegistry",
    "discover_plugins",
    "console",
    "arrow_select",
    "AVAILABLE_GPUS",
    "AVAILABLE_CPUS",
    "METRICS_FUNCTIONS",
    "MODAL_CONFIG_PATH",
    "MONTHLY_CREDIT",
    "load_config",
    "save_config",
    "load_profiles",
    "select_profile",
    "activate_profile",
    "get_all_profiles",
    "get_best_profile",
    "get_all_balances",
    "execute_modal_temp_script",
    "scan_apps_across_profiles",
    "_select_profile",
    "_activate_profile",
    "_load_profiles",
]
