"""
Signal Authorization.
Shared by signal_bot.py and every handlers/*.py module -- kept independent of
signal_bot.py itself so handler modules never need to import back from the
entrypoint (which would create a circular import).
"""

import os

SIGNAL_ALLOWED_NUMBER = os.environ.get("SIGNAL_ALLOWED_PHONE_NUMBER", "")


def is_authorized(sender: str) -> bool:
    """Verifies that incoming Signal phone number matches SIGNAL_ALLOWED_NUMBER."""
    if not SIGNAL_ALLOWED_NUMBER:
        return True
    if not sender:
        return False
    return sender.strip().replace(" ", "").replace("-", "") == SIGNAL_ALLOWED_NUMBER.strip().replace(" ", "").replace("-", "")
