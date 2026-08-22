"""
Test stubs and mock environment setup for isolated testing.
"""

import sys
from unittest.mock import MagicMock

# Mock external network and third-party bot libraries if not present in test environment
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
