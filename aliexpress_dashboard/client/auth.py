"""Builds the URL for the OAuth authorize step.

Confirmed from AliExpress's own OAuth documentation, not guessed:

    https://api-sg.aliexpress.com/oauth/authorize
        ?response_type=code&force_auth=true
        &redirect_url=<callback URL registered on the app>
        &client_id=<app_key>

Opening this URL, logging in, and clicking "Authorize" redirects the
browser to the callback URL with a `code` query parameter attached --
short-lived, so exchange it for a token promptly (AliClient.exchange_code_for_token).

Confirmed against a real account: the resulting access token is valid only
24 hours (refresh token 48 hours), not the ~365 days the docs implied for a
self-developed app -- this needs re-authorizing roughly daily, or a
scheduled `refresh-token` call before the 48-hour window closes. See
client/tokens.py and the README.
"""

from __future__ import annotations

from urllib.parse import urlencode

_AUTHORIZE_URL = "https://api-sg.aliexpress.com/oauth/authorize"


def build_authorize_url(*, app_key: str, callback_url: str) -> str:
    params = {
        "response_type": "code",
        "force_auth": "true",
        "redirect_url": callback_url,
        "client_id": app_key,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"
