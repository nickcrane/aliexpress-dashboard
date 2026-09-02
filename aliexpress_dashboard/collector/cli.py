"""Collector CLI.

    python -m aliexpress_dashboard.collector.cli add-search --name ...
    python -m aliexpress_dashboard.collector.cli list-searches
    python -m aliexpress_dashboard.collector.cli run [--search NAME]
    python -m aliexpress_dashboard.collector.cli authorize [--code CODE]
    python -m aliexpress_dashboard.collector.cli refresh-token

Safe to invoke repeatedly on a schedule (cron, launchd, APScheduler, ...):
each invocation opens the database, applies any pending migrations, creates
one new `runs` row, and upserts products/observations -- see runner.py for
the idempotency guarantee within a single run.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Optional, Sequence

from ..client import build_authorize_url
from ..client.ali_client import AliClient
from ..config import get_settings
from ..db.connection import get_connection
from ..db.migrate import run_migrations
from . import store
from .runner import run_collection

logger = logging.getLogger(__name__)

_VALID_SORTS = [
    "min_price,asc",
    "min_price,desc",
    "orders,asc",
    "orders,desc",
    "comments,asc",
    "comments,desc",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aliexpress-dashboard-collector")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the collector")
    run_parser.add_argument("--search", help="Run only this saved search, active or not")

    add_parser = subparsers.add_parser("add-search", help="Create or update a saved search")
    add_parser.add_argument("--name", required=True)
    add_parser.add_argument("--keywords")
    add_parser.add_argument("--category-id", type=int, dest="category_id")
    add_parser.add_argument("--min-price", type=float, dest="min_price")
    add_parser.add_argument("--max-price", type=float, dest="max_price")
    add_parser.add_argument("--currency", help="Currency the price band is denominated in")
    add_parser.add_argument("--sort", choices=_VALID_SORTS)
    add_parser.add_argument("--ship-to", dest="ship_to_country", help="Overrides the default ship-to country")
    add_parser.add_argument("--selection-name", dest="selection_name")
    add_parser.add_argument(
        "--inactive", action="store_true", help="Save disabled (excluded from `run` without --search)"
    )

    subparsers.add_parser("list-searches", help="List saved searches")

    authorize_parser = subparsers.add_parser(
        "authorize", help="One-time OAuth setup: print the authorize URL, or exchange a code for a token"
    )
    authorize_parser.add_argument(
        "--code", help="The `code` copied from the browser's address bar after authorizing"
    )

    subparsers.add_parser("refresh-token", help="Refresh the stored access token using the saved refresh token")

    return parser


def _cmd_add_search(args: argparse.Namespace, conn) -> int:
    if (args.min_price is not None or args.max_price is not None) and not args.currency:
        print("--currency is required when --min-price/--max-price is set", file=sys.stderr)
        return 2

    store.upsert_search(
        conn,
        name=args.name,
        keywords=args.keywords,
        category_id=args.category_id,
        min_price=args.min_price,
        max_price=args.max_price,
        price_currency=args.currency,
        sort=args.sort,
        ship_to_country=args.ship_to_country,
        selection_name=args.selection_name,
        is_active=not args.inactive,
    )
    print(f"Saved search {args.name!r}")
    return 0


def _cmd_list_searches(conn) -> int:
    searches = store.list_all_searches(conn)
    if not searches:
        print("No saved searches yet. Use add-search to create one.")
        return 0
    for saved in searches:
        status = "active" if saved.is_active else "inactive"
        print(f"{saved.id}\t{saved.params.name}\t{status}")
    return 0


def _cmd_run(args: argparse.Namespace, conn, settings) -> int:
    if args.search:
        saved = store.get_search_by_name(conn, args.search)
        if saved is None:
            print(
                f"No saved search named {args.search!r}. Use list-searches to see what's defined.",
                file=sys.stderr,
            )
            return 2
        searches = [saved]
    else:
        searches = store.load_active_searches(conn)
        if not searches:
            print("No active searches defined. Use add-search to create one.", file=sys.stderr)
            return 0

    client = AliClient(settings)
    summary = run_collection(conn, client, mode=settings.mode, searches=searches)

    print(
        f"run {summary.run_id}: {summary.searches_executed} searches executed, "
        f"{summary.records_written} records written, {len(summary.errors)} errors"
    )
    for error in summary.errors:
        print(f"  ERROR [{error['search_name']}]: {error['error']}")

    return 1 if summary.errors else 0


def _cmd_authorize(args: argparse.Namespace, settings) -> int:
    if not settings.app_key:
        print("AE_APP_KEY must be set in .env first.", file=sys.stderr)
        return 2

    if not args.code:
        url = build_authorize_url(app_key=settings.app_key, callback_url=settings.callback_url)
        print("1. Open this URL in a browser and log in:\n")
        print(f"   {url}\n")
        print("2. Click Authorize. You'll be redirected to your callback URL.")
        print("3. Copy the `code` value from the browser's address bar.")
        print("4. Run: python -m aliexpress_dashboard.collector.cli authorize --code <code>")
        return 0

    client = AliClient(settings)
    token = client.exchange_code_for_token(args.code)
    print(f"Authorized. Access token saved to {settings.token_path}")
    print(f"Valid for {token.expires_in} seconds; refresh token valid for {token.refresh_expires_in} seconds.")
    return 0


def _cmd_refresh_token(settings) -> int:
    client = AliClient(settings)
    token = client.refresh_access_token()
    print(f"Refreshed. Access token saved to {settings.token_path}")
    print(f"Valid for {token.expires_in} seconds; refresh token valid for {token.refresh_expires_in} seconds.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    args = _build_parser().parse_args(argv)
    settings = get_settings()

    if args.command == "authorize":
        return _cmd_authorize(args, settings)
    if args.command == "refresh-token":
        return _cmd_refresh_token(settings)

    conn = get_connection(settings.db_path)
    run_migrations(conn)

    if args.command == "add-search":
        return _cmd_add_search(args, conn)
    if args.command == "list-searches":
        return _cmd_list_searches(conn)
    if args.command == "run":
        return _cmd_run(args, conn, settings)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
