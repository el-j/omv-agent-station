"""
Signal Outbound Messaging.
Shared by signal_bot.py and every handlers/*.py module -- kept independent of
signal_bot.py itself so handler modules never need to import back from the
entrypoint (which would create a circular import).
"""

import os

import httpx

from agent_station_core import logger

SIGNAL_API_URL = os.environ.get("SIGNAL_CLI_URL", "http://signal-cli:8080")
SIGNAL_PHONE_NUMBER = os.environ.get("SIGNAL_PHONE_NUMBER", "")


async def send_signal_message(recipient: str, message: str):
    """Sends an end-to-end encrypted message via signal-cli REST API."""
    url = f"{SIGNAL_API_URL.rstrip('/')}/v2/send"
    payload = {
        "number": SIGNAL_PHONE_NUMBER,
        "recipients": [recipient],
        "message": message
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code not in (200, 201):
                logger.warning(f"Failed to send Signal message: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Error sending Signal message to {recipient}: {e}")
