"""
Kai chat integration — the ONLY part that needs a Keboola master token.
=======================================================================
The app's auto-provisioned Storage token is NOT enough for the Kai client; Kai
currently requires a MASTER token. Provide it as a secret env var STORAGE_API_TOKEN
in the data app configuration. STORAGE_API_URL defaults to the EU stack.

SECURITY: a master token = full admin access to project 855. If it leaks, that is
full-project compromise, and it can only be revoked by removing the user from the
project. Recommended: create a dedicated service admin user (e.g. kai-app@tribe.xyz)
and use ITS master token here, never a personal one. Never log this value.

This module is intentionally defensive: if the token or the kai_client package is
missing, the app still runs and the chat box reports "not configured".
"""

import os

# Keboola injects a `#`-prefixed secret decrypted at runtime; accept either env var name.
STORAGE_API_TOKEN = os.environ.get("STORAGE_API_TOKEN") or os.environ.get("#STORAGE_API_TOKEN")  # MASTER token (secret)
STORAGE_API_URL = os.environ.get("STORAGE_API_URL", "https://connection.eu-central-1.keboola.com")


def is_configured():
    """True only if a token is present AND the kai client library is importable."""
    if not STORAGE_API_TOKEN:
        return False
    try:
        import kai_client  # noqa: F401
        return True
    except ImportError:
        return False


def ask(question: str) -> str:
    """Send one question to Kai and return the full text answer (blocking)."""
    import asyncio, traceback

    token_names = [k for k in os.environ if "TOKEN" in k.upper() or "STORAGE" in k.upper()]
    print(f"[kai] token env names seen={token_names} configured={is_configured()}", flush=True)

    if not is_configured():
        return "Kai is not configured. Set the STORAGE_API_TOKEN (master token) secret."

    from kai_client import KaiClient

    async def _run():
        client = await KaiClient.from_storage_api(
            storage_api_token=STORAGE_API_TOKEN,
            storage_api_url=STORAGE_API_URL,
        )
        async with client:
            chat_id = client.new_chat_id()
            out = ""
            counts = {}
            # Kai runs an agent loop (tool calls between turns). Consume the WHOLE stream
            # so we capture the final answer after the tool calls, not just the preamble.
            