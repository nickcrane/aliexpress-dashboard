"""Wrapper around the aliexpress.ds.* ("AE-Dropshipper") API family.

python-aliexpress-api has no SDK support for this family at all -- every
request class it ships is aliexpress.affiliate.*, which this app's AliExpress
account has no permission to call (confirmed: the app's only granted
permission groups are "System Tool" and "Drop Shipping"). So the request
classes below are hand-built, following the exact same pattern the
library's own generated classes use (subclassing `RestApi`, letting it
reflect over `self.__dict__` to build the signed request) -- that pattern,
the MD5 signature, and the TOP gateway domain are still worth reusing;
only the affiliate-specific SDK classes and response envelope aren't.

The response envelope turns out to be inconsistent across this API family,
confirmed live rather than assumed from the docs: aliexpress.ds.product.get
returns `{result: {...}, rsp_code, rsp_msg}` directly, matching its docs;
aliexpress.ds.text.search and the /auth/token/* endpoints instead wrap
everything in `{"<api_name>_response": {...}}`, the same convention the
affiliate family used, contradicting their own docs' flatter example JSON.
This bypasses `aliexpress_api.helpers.api_request()` entirely (it's written
for the affiliate family's specific nesting, one level different from any
of the above) and does its own envelope handling in `_call_ds_api()` below,
auto-detecting the wrapper rather than hardcoding it per endpoint.

ds.* calls also require a user OAuth access_token (`authrize=` on
`RestApi.getResponse()`), which the affiliate family never needed -- see
client/auth.py and client/tokens.py for the one-time authorization flow.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import List, Optional

from aliexpress_api.errors.exceptions import ApiRequestException, ApiRequestResponseException
from aliexpress_api.skd import setDefaultAppInfo
from aliexpress_api.skd.api.base import RestApi

from ..config import Settings
from .errors import FixtureNotFoundError, TokenMissingError
from .models import NormalizedCategory, NormalizedProduct, SearchParams, SearchResult, TokenSet
from .normalize import normalize_category, normalize_detail_product, normalize_search_product
from .raw import extract_list, get_field
from .tokens import load_token, now_iso, save_token, seed_token_from_env

logger = logging.getLogger(__name__)

_DOMAIN = "api-sg.aliexpress.com"
_HTTPS_PORT = 443


class _DsTextSearchRequest(RestApi):
    def __init__(self, domain=_DOMAIN, port=_HTTPS_PORT):
        RestApi.__init__(self, domain, port)
        self.app_signature = None
        self.keyWord = None
        self.local = None
        self.countryCode = None
        self.categoryId = None
        self.sortBy = None
        self.pageSize = None
        self.pageIndex = None
        self.currency = None
        self.searchExtend = None
        self.selectionName = None

    def getapiname(self):
        return "aliexpress.ds.text.search"


class _DsProductGetRequest(RestApi):
    def __init__(self, domain=_DOMAIN, port=_HTTPS_PORT):
        RestApi.__init__(self, domain, port)
        self.app_signature = None
        self.ship_to_country = None
        self.product_id = None
        self.target_currency = None
        self.target_language = None

    def getapiname(self):
        return "aliexpress.ds.product.get"


class _DsCategoryGetRequest(RestApi):
    def __init__(self, domain=_DOMAIN, port=_HTTPS_PORT):
        RestApi.__init__(self, domain, port)
        self.app_signature = None

    def getapiname(self):
        return "aliexpress.ds.category.get"


class _AuthTokenCreateRequest(RestApi):
    def __init__(self, domain=_DOMAIN, port=_HTTPS_PORT):
        RestApi.__init__(self, domain, port)
        self.code = None

    def getapiname(self):
        return "/auth/token/create"


class _AuthTokenRefreshRequest(RestApi):
    def __init__(self, domain=_DOMAIN, port=_HTTPS_PORT):
        RestApi.__init__(self, domain, port)
        self.refresh_token = None

    def getapiname(self):
        return "/auth/token/refresh"


def _unwrap_envelope(envelope: dict) -> dict:
    """TOP-gateway responses wrap the real payload under one or two levels
    of nesting -- confirmed live, and inconsistent per endpoint:

    - aliexpress.ds.product.get: no wrapping, `{result, rsp_code, rsp_msg}` directly.
    - aliexpress.ds.text.search, /auth/token/*: one level, a single-key
      `{"<api_name>_response": {...}}`.
    - aliexpress.ds.category.get: two levels -- the same single-key
      "_response" wrapper, then a "resp_result" key *alongside siblings*
      like request_id/_trace_id_ (not itself single-keyed), holding the
      actual `{result, resp_code, resp_msg}`.

    Strips the single-key "_response" wrapper first, then a "resp_result"
    key if present regardless of its siblings -- more resilient than
    hardcoding each endpoint's exact nesting, especially since this hasn't
    been exhaustively checked against every endpoint.
    """
    if isinstance(envelope, dict) and len(envelope) == 1:
        ((key, value),) = envelope.items()
        if key.endswith("_response") and isinstance(value, dict):
            envelope = value
    if isinstance(envelope, dict) and isinstance(envelope.get("resp_result"), dict):
        envelope = envelope["resp_result"]
    return envelope


def _is_success_code(code) -> bool:
    """A confirmed-live response used "00" for success, not the "0" the
    library's own affiliate-family convention and this app's other error
    checks use -- treat any all-zeros code (and a missing one) as success
    rather than hardcoding one specific string."""
    if code is None:
        return True
    if isinstance(code, (int, float)):
        return code == 0
    if isinstance(code, str):
        return code.strip() == "" or set(code.strip()) == {"0"}
    return False


def _call_ds_api(request: RestApi, *, access_token: Optional[str] = None) -> dict:
    """Signs and sends a request, returning the unwrapped response dict.

    Deliberately doesn't reuse aliexpress_api.helpers.api_request() -- it's
    written for the affiliate family's specific envelope shape
    (`{<method>_response: {resp_result: {...}}}`), one level deeper than
    what's actually observed here. RestApi.getResponse() (signing + HTTP +
    json.loads()) is still the part worth reusing; the envelope handling
    below is this client's own.
    """
    try:
        response = request.getResponse(authrize=access_token)
    except Exception as exc:  # noqa: BLE001 - re-raised as our own typed exception below
        if hasattr(exc, "message"):
            raise ApiRequestException(exc.message) from exc
        raise ApiRequestException(exc) from exc

    response = _unwrap_envelope(response)

    # Different endpoints in this family signal success under different
    # field names, confirmed live: aliexpress.ds.text.search uses "code"
    # ("00" for success), aliexpress.ds.product.get uses "rsp_code" ("200"),
    # aliexpress.ds.category.get uses "resp_code" (200, an int, not a
    # string) -- genuinely three different names, not a typo. Check
    # whichever is present; a response with none of them is treated as
    # successful rather than guessed at.
    for code_field, message_field in (("code", "msg"), ("rsp_code", "rsp_msg"), ("resp_code", "resp_msg")):
        if code_field not in response:
            continue
        code = response.get(code_field)
        success = _is_success_code(code) if code_field == "code" else str(code) in ("200", "0", "00")
        if not success:
            message = response.get(message_field) or response.get("sub_msg") or "unknown error"
            raise ApiRequestResponseException(f"AliExpress API error {code}: {message}")

    return response


class AliClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._last_request_at = 0.0
        # Bootstraps a fresh deployment (e.g. a new Railway volume with no
        # token file yet) from AE_TOKEN_SEED; a no-op once the file exists.
        seed_token_from_env(settings.token_path, settings.token_seed)
        # Loaded regardless of mode -- this is just local state (has a prior
        # authorize/refresh call already saved a token?), not a live API call.
        self._token: Optional[TokenSet] = load_token(settings.token_path)
        if settings.mode == "live":
            setDefaultAppInfo(settings.app_key, settings.app_secret)

    # -- public API ------------------------------------------------------

    def search_products(self, params: SearchParams) -> SearchResult:
        if self._settings.mode == "fixture":
            envelope = self._load_fixture(self._fixture_path("text_search", self._fixture_name(params)))
        else:
            envelope = self._with_retries(lambda: self._call_text_search(params))

        data = get_field(envelope, "data") or {}
        raw_products = extract_list(get_field(data, "products"))
        products = [normalize_search_product(raw, target_currency=self._settings.target_currency) for raw in raw_products]

        return SearchResult(
            products=products,
            current_page_no=int(get_field(data, "pageIndex", params.page_no) or params.page_no),
            current_record_count=len(products),
            total_record_count=int(get_field(data, "totalCount", len(products)) or 0),
        )

    def get_product_detail(self, product_id: int) -> Optional[NormalizedProduct]:
        if self._settings.mode == "fixture":
            envelope = self._load_fixture(self._fixture_path("product_detail", str(product_id)))
        else:
            envelope = self._with_retries(lambda: self._call_product_get(product_id))

        result = get_field(envelope, "result")
        if not result:
            return None
        return normalize_detail_product(result, target_currency=self._settings.target_currency)

    def get_categories(self) -> List[NormalizedCategory]:
        """Confirmed live: aliexpress.ds.category.get returns a flat list of
        {category_id, category_name, parent_category_id?} objects (parent
        absent on top-level categories), matching the shape this always
        assumed -- it's the envelope around it that needed real data to get
        right (see _unwrap_envelope)."""
        if self._settings.mode == "fixture":
            envelope = self._load_fixture(self._settings.fixtures_dir / "categories.json")
        else:
            envelope = self._with_retries(self._call_category_get)

        result = get_field(envelope, "result") or get_field(envelope, "data")
        raw_categories = extract_list(get_field(result, "categories") if result is not None else None)
        return [normalize_category(raw) for raw in raw_categories]

    # -- OAuth -------------------------------------------------------------

    def exchange_code_for_token(self, code: str) -> TokenSet:
        if self._settings.mode == "fixture":
            envelope = self._load_fixture(self._settings.fixtures_dir / "auth" / "token_create.json")
        else:
            request = _AuthTokenCreateRequest()
            request.code = code
            envelope = _call_ds_api(request)
        token = _token_set_from_envelope(envelope)
        save_token(self._settings.token_path, token)
        self._token = token
        return token

    def refresh_access_token(self) -> TokenSet:
        if self._token is None or not self._token.refresh_token:
            raise TokenMissingError("No refresh token on file -- run the authorize step again.")
        if self._settings.mode == "fixture":
            envelope = self._load_fixture(self._settings.fixtures_dir / "auth" / "token_refresh.json")
        else:
            request = _AuthTokenRefreshRequest()
            request.refresh_token = self._token.refresh_token
            envelope = _call_ds_api(request)
        token = _token_set_from_envelope(envelope)
        save_token(self._settings.token_path, token)
        self._token = token
        return token

    # -- live request construction ---------------------------------------

    def _access_token(self) -> str:
        if self._token is None:
            raise TokenMissingError(
                "No access token on file. Run the authorize step first: "
                "python -m aliexpress_dashboard.collector.cli authorize"
            )
        return self._token.access_token

    def _call_text_search(self, params: SearchParams) -> dict:
        request = _DsTextSearchRequest()
        request.keyWord = params.keywords
        request.local = self._settings.target_language
        request.countryCode = params.ship_to_country or self._settings.ship_to_country
        request.categoryId = params.category_id
        request.sortBy = params.sort
        request.pageSize = params.page_size
        request.pageIndex = params.page_no
        request.currency = self._settings.target_currency
        request.selectionName = params.selection_name
        if params.min_price is not None or params.max_price is not None:
            # Confirmed live this doesn't actually filter (see SearchParams
            # docstring) -- still sent since it's harmless and costs nothing.
            request.searchExtend = json.dumps(
                [
                    {
                        "searchKey": "price",
                        "min": params.min_price,
                        "max": params.max_price,
                    }
                ]
            )
        return _call_ds_api(request, access_token=self._access_token())

    def _call_product_get(self, product_id: int) -> dict:
        request = _DsProductGetRequest()
        request.ship_to_country = self._settings.ship_to_country
        request.product_id = product_id
        request.target_currency = self._settings.target_currency
        request.target_language = self._settings.target_language
        return _call_ds_api(request, access_token=self._access_token())

    def _call_category_get(self) -> dict:
        request = _DsCategoryGetRequest()
        return _call_ds_api(request, access_token=self._access_token())

    # -- fixture loading ---------------------------------------------------

    @staticmethod
    def _fixture_name(params: SearchParams) -> str:
        if params.page_no and params.page_no > 1:
            return f"{params.name}_page{params.page_no}"
        return params.name

    def _fixture_path(self, subdir: str, name: str) -> Path:
        return self._settings.fixtures_dir / subdir / f"{name}.json"

    @staticmethod
    def _load_fixture(path: Path) -> dict:
        if not path.exists():
            available = sorted(p.stem for p in path.parent.glob("*.json")) if path.parent.exists() else []
            raise FixtureNotFoundError(f"No fixture at {path}. Available in {path.parent}: {available}")
        return _unwrap_envelope(json.loads(path.read_text()))

    # -- throttling and retry ----------------------------------------------

    def _throttle(self) -> None:
        min_interval = self._settings.rate_limit.min_request_interval_seconds
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _with_retries(self, call):
        rate_limit = self._settings.rate_limit
        attempt = 0
        while True:
            self._throttle()
            try:
                return call()
            except (ApiRequestException, ApiRequestResponseException, OSError) as exc:
                attempt += 1
                if attempt > rate_limit.max_retries:
                    raise
                delay = min(
                    rate_limit.backoff_base_seconds * (2 ** (attempt - 1)),
                    rate_limit.backoff_max_seconds,
                )
                logger.warning(
                    "AliExpress API call failed (attempt %s/%s): %s. Retrying in %.1fs",
                    attempt,
                    rate_limit.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)




def _token_set_from_envelope(envelope: dict) -> TokenSet:
    return TokenSet(
        access_token=envelope["access_token"],
        refresh_token=envelope.get("refresh_token"),
        expires_in=_int_or_none(envelope.get("expires_in")),
        refresh_expires_in=_int_or_none(envelope.get("refresh_expires_in")),
        obtained_at=now_iso(),
    )


def _int_or_none(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
