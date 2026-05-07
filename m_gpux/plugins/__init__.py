"""Built-in plugin registry.

Add a new built-in plugin by appending its dotted ``module:ClassName`` string
to :data:`BUILTIN_PLUGINS`.

Third-party plugins should NOT be added here — they are expected to register
themselves through the ``m_gpux.plugins`` Python entry-point group. See
:mod:`m_gpux.core.plugin` for details.
"""

BUILTIN_PLUGINS: list[str] = [
    "m_gpux.plugins.account.plugin:AccountPlugin",
    "m_gpux.plugins.billing.plugin:BillingPlugin",
    "m_gpux.plugins.compose.plugin:ComposePlugin",
    "m_gpux.plugins.dev.plugin:DevPlugin",
    "m_gpux.plugins.hub.plugin:HubPlugin",
    "m_gpux.plugins.host.plugin:HostPlugin",
    "m_gpux.plugins.load.plugin:LoadPlugin",
    "m_gpux.plugins.preset.plugin:PresetPlugin",
    "m_gpux.plugins.serve.plugin:ServePlugin",
    "m_gpux.plugins.sessions.plugin:SessionsPlugin",
    "m_gpux.plugins.video.plugin:VideoPlugin",
    "m_gpux.plugins.vision.plugin:VisionPlugin",
    "m_gpux.plugins.info.plugin:InfoPlugin",
    "m_gpux.plugins.stop.plugin:StopPlugin",
]
