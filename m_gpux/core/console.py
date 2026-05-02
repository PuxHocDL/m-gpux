"""Shared :class:`rich.console.Console` instance.

Plugins should use this instance instead of constructing their own so that
output redirection / theming can be applied centrally in the future.
"""

from rich.console import Console

console: Console = Console()
