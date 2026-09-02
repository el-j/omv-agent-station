"""
Test stubs and mock environment setup for isolated testing.
"""

import sys
from unittest.mock import MagicMock

# Mock external network and third-party bot libraries if not present in test environment
_mocked_commands_module = False
_mocked_discord_module = False
for mod_name in [
    "telegram",
    "telegram.ext",
    "discord",
    "discord.ext",
    "discord.ext.commands",
    "openai",
    "httpx",
    "websockets"
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
        if mod_name == "discord.ext.commands":
            _mocked_commands_module = True
        elif mod_name == "discord":
            _mocked_discord_module = True


class _StubThread:
    """A real class standing in for discord.Thread, so isinstance() checks
    (e.g. discord_bot.py's channel_scope()) work against a mocked `discord`
    module instead of raising -- a plain MagicMock isn't a type."""


if _mocked_discord_module:
    sys.modules["discord"].Thread = _StubThread


class _StubBot(MagicMock):
    """A commands.Bot stand-in whose @bot.command()/@bot.event decorators are
    identity functions, so decorated handlers stay the real, directly
    callable coroutine instead of collapsing into one shared MagicMock
    (a plain MagicMock's .command()(func) discards func and always returns
    the same cached .return_value, regardless of what was decorated)."""

    def command(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def event(self, func):
        return func


if _mocked_commands_module:
    # Real discord.py commands.Bot instances are callables that still expose
    # the decorated function afterwards; this stand-in just returns the
    # function unchanged so `discord_bot.exec_cmd` etc. are the real coroutine.
    sys.modules["discord.ext.commands"].Bot = _StubBot
    # "discord.ext" is a bare MagicMock, not a real package, so
    # `from discord.ext import commands` resolves via attribute access
    # (auto-vivifying an unrelated mock) rather than through sys.modules --
    # point the parent's .commands attribute at the same module we just
    # configured so both import styles see the identical object.
    sys.modules["discord.ext"].commands = sys.modules["discord.ext.commands"]


def purge_bot_modules(*module_names):
    """Evicts the given top-level module names (and any dotted submodules
    under them) from sys.modules.

    discord-agent-bot/, signal-agent-bot/, and telegram-agent-bot/ each ship
    their own `core`/`handlers` packages with the SAME import names (by
    design -- issue #22 mirrors Telegram's structure onto Discord/Signal).
    Each bot runs as its own isolated process in production, so this never
    collides for real, but the test suite imports all three into one shared
    interpreter via sys.path tricks -- so whichever bot's `core`/`handlers`
    happened to be imported first would otherwise "win" for the rest of the
    process. Call this in setUp (before importing) and tearDown (after
    removing the bot dir from sys.path) so every test starts and ends with
    a clean slate regardless of run order.
    """
    for name in list(sys.modules):
        if any(name == m or name.startswith(m + ".") for m in module_names):
            del sys.modules[name]
