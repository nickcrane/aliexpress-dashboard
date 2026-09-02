from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field, replace
from typing import List

from ..client.ali_client import AliClient
from ..client.models import NormalizedProduct, SearchParams, SearchResult
from . import store
from .store import SavedSearch, now_iso

logger = logging.getLogger(__name__)

# 20 pages * the API's max page_size (50) = 1000 products per search per run.
# A safety cap, not an expected ceiling -- guards against an unbounded loop
# if total_record_count is ever wrong or a page keeps returning results.
MAX_PAGES_PER_SEARCH = 20


@dataclass
class RunSummary:
    run_id: int
    searches_executed: int
    records_written: int
    errors: List[dict] = field(default_factory=list)


def _call_page(client: AliClient, params: SearchParams) -> SearchResult:
    return client.search_products(params)


def _fetch_all_pages(client: AliClient, params: SearchParams) -> SearchResult:
    """Fetches every page of a search's results, not just the first.

    A later page failing after earlier pages already succeeded keeps what
    was already collected rather than discarding it -- only a failure on the
    very first page is a genuine search failure with nothing to salvage,
    which is exactly how a single-page search already behaved. This mirrors
    the "one bad thing doesn't erase the good data already in hand"
    principle the per-search error handling in run_collection follows.
    """
    all_products: List[NormalizedProduct] = []
    page_no = params.page_no or 1
    current_page_no = page_no
    total_record_count = 0

    for page_index in range(MAX_PAGES_PER_SEARCH):
        try:
            result = _call_page(client, replace(params, page_no=page_no))
        except Exception as exc:  # noqa: BLE001 - see docstring
            if page_index == 0:
                raise
            logger.warning(
                "search %r: page %s failed after %s page(s) already collected (%s); keeping what's in hand",
                params.name,
                page_no,
                page_index,
                exc,
            )
            break

        all_products.extend(result.products)
        current_page_no = result.current_page_no
        total_record_count = result.total_record_count

        if len(all_products) >= total_record_count or not result.products:
            break
        page_no += 1
    else:
        logger.warning(
            "search %r: hit the %s-page safety cap with more results remaining (total_record_count=%s)",
            params.name,
            MAX_PAGES_PER_SEARCH,
            total_record_count,
        )

    return SearchResult(
        products=all_products,
        current_page_no=current_page_no,
        current_record_count=len(all_products),
        total_record_count=total_record_count,
    )


def run_collection(
    conn: sqlite3.Connection,
    client: AliClient,
    *,
    mode: str,
    searches: List[SavedSearch],
) -> RunSummary:
    """Runs every given saved search and writes results to SQLite.

    One search's failure is caught and recorded in the run's error log; it
    does not stop the remaining searches from running. Each product write is
    an upsert keyed on (product_id, run_id), so re-running this on the same
    saved searches within one run never creates duplicate observation rows --
    running the whole collector again later (a new run_id) is expected to add
    a fresh, legitimate observation per product, not to be blocked.
    """
    run_id = store.create_run(conn, mode=mode)

    searches_executed = 0
    records_written = 0
    errors: List[dict] = []

    for saved in searches:
        searches_executed += 1
        try:
            result = _fetch_all_pages(client, saved.params)
        except Exception as exc:  # noqa: BLE001 - one bad search must not abort the run
            logger.warning("search %r failed: %s", saved.params.name, exc)
            errors.append({"search_name": saved.params.name, "error": str(exc)})
            continue

        captured_at = now_iso()
        for product in result.products:
            store.upsert_product_and_observation(
                conn,
                product,
                run_id=run_id,
                search_id=saved.id,
                captured_at=captured_at,
            )
            records_written += 1
        conn.commit()

    store.finish_run(
        conn,
        run_id,
        searches_executed=searches_executed,
        records_written=records_written,
        errors=errors,
    )

    return RunSummary(
        run_id=run_id,
        searches_executed=searches_executed,
        records_written=records_written,
        errors=errors,
    )
