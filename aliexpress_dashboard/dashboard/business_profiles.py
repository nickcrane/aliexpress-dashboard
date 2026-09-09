"""Multi-tenant, versioned business-plan onboarding: a Firebase email (see
spa/security.py -- that's the only user identity this app has) can have
many saved plans. At most one is "active" per user at a time (enforced by
a partial unique index -- see db/migrations/0006_business_profile_versions.sql)
-- that's the one dashboard/queries.py-adjacent callers read to drive
default filters/sort weights on the Products page. Editing a specific
version updates it in place; creating a new one never overwrites an
existing row.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import List, Optional

_FIELDS = (
    "seller_type",
    "product_niche",
    "target_market",
    "sales_channels",
    "marketing_approach",
    "budget_stage",
    "experience_level",
    "primary_category_id",
    "summary",
    "market_gap_analysis",
    "status",
)


@dataclass
class BusinessProfile:
    user_email: str
    id: Optional[int] = None
    seller_type: Optional[str] = None
    product_niche: Optional[str] = None
    target_market: Optional[str] = None
    sales_channels: List[str] = field(default_factory=list)
    marketing_approach: List[str] = field(default_factory=list)
    budget_stage: Optional[str] = None
    experience_level: Optional[str] = None
    primary_category_id: Optional[int] = None
    summary: Optional[str] = None
    market_gap_analysis: Optional[str] = None
    status: str = "in_progress"
    is_active: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _row_to_profile(row: sqlite3.Row) -> BusinessProfile:
    return BusinessProfile(
        id=row["id"],
        user_email=row["user_email"],
        seller_type=row["seller_type"],
        product_niche=row["product_niche"],
        target_market=row["target_market"],
        sales_channels=json.loads(row["sales_channels"]) if row["sales_channels"] else [],
        marketing_approach=json.loads(row["marketing_approach"]) if row["marketing_approach"] else [],
        budget_stage=row["budget_stage"],
        experience_level=row["experience_level"],
        primary_category_id=row["primary_category_id"],
        summary=row["summary"],
        market_gap_analysis=row["market_gap_analysis"],
        status=row["status"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_business_profiles(conn: sqlite3.Connection, user_email: str) -> List[BusinessProfile]:
    rows = conn.execute(
        "SELECT * FROM business_profiles WHERE user_email = ? ORDER BY created_at DESC", (user_email,)
    ).fetchall()
    return [_row_to_profile(row) for row in rows]


def get_active_business_profile(conn: sqlite3.Connection, user_email: str) -> Optional[BusinessProfile]:
    row = conn.execute(
        "SELECT * FROM business_profiles WHERE user_email = ? AND is_active = 1", (user_email,)
    ).fetchone()
    return _row_to_profile(row) if row else None


def get_business_profile_by_id(conn: sqlite3.Connection, profile_id: int) -> Optional[BusinessProfile]:
    row = conn.execute("SELECT * FROM business_profiles WHERE id = ?", (profile_id,)).fetchone()
    return _row_to_profile(row) if row else None


def _values(profile: BusinessProfile) -> dict:
    return {
        "seller_type": profile.seller_type,
        "product_niche": profile.product_niche,
        "target_market": profile.target_market,
        "sales_channels": json.dumps(profile.sales_channels),
        "marketing_approach": json.dumps(profile.marketing_approach),
        "budget_stage": profile.budget_stage,
        "experience_level": profile.experience_level,
        "primary_category_id": profile.primary_category_id,
        "summary": profile.summary,
        "market_gap_analysis": profile.market_gap_analysis,
        "status": profile.status,
    }


def create_business_profile(conn: sqlite3.Connection, profile: BusinessProfile, *, make_active: bool) -> int:
    """Always inserts a new version -- never overwrites an existing row.
    If make_active, clears is_active on this user's other versions first
    (in the same transaction), so the partial unique index is never
    violated and the new row cleanly becomes the sole active one."""
    if make_active:
        conn.execute("UPDATE business_profiles SET is_active = 0 WHERE user_email = ?", (profile.user_email,))
    values = _values(profile)
    values["user_email"] = profile.user_email
    values["is_active"] = 1 if make_active else 0
    cursor = conn.execute(
        f"""
        INSERT INTO business_profiles (user_email, {", ".join(_FIELDS)}, is_active)
        VALUES (:user_email, {", ".join(f":{col}" for col in _FIELDS)}, :is_active)
        """,
        values,
    )
    conn.commit()
    return cursor.lastrowid


def update_business_profile(conn: sqlite3.Connection, profile_id: int, profile: BusinessProfile) -> None:
    """Edits an existing version in place -- does not change which
    version is active."""
    values = _values(profile)
    values["id"] = profile_id
    set_clause = ",\n            ".join(f"{col}=:{col}" for col in _FIELDS)
    conn.execute(
        f"UPDATE business_profiles SET {set_clause}, updated_at=datetime('now') WHERE id=:id",
        values,
    )
    conn.commit()


def set_active_business_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    """Derives the owning user_email from the profile itself rather than
    taking it as a caller-supplied argument -- callers should already
    have verified ownership (see api/app.py's _require_owned_profile)
    before calling this; this just needs to know which sibling rows to
    deactivate."""
    row = conn.execute("SELECT user_email FROM business_profiles WHERE id = ?", (profile_id,)).fetchone()
    if row is None:
        return
    conn.execute("UPDATE business_profiles SET is_active = 0 WHERE user_email = ?", (row["user_email"],))
    conn.execute("UPDATE business_profiles SET is_active = 1 WHERE id = ?", (profile_id,))
    conn.commit()


def delete_business_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    conn.execute("DELETE FROM business_profiles WHERE id = ?", (profile_id,))
    conn.commit()
