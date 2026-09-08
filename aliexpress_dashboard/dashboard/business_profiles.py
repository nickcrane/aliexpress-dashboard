"""Multi-tenant business-plan onboarding: one profile per Firebase email
(see spa/security.py -- that's the only user identity this app has).
Deliberately schema-shaped (not free text) so it can drive default
filters/sort weights on the Products page, not just be displayed back.
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
    "status",
)


@dataclass
class BusinessProfile:
    user_email: str
    seller_type: Optional[str] = None
    product_niche: Optional[str] = None
    target_market: Optional[str] = None
    sales_channels: List[str] = field(default_factory=list)
    marketing_approach: List[str] = field(default_factory=list)
    budget_stage: Optional[str] = None
    experience_level: Optional[str] = None
    primary_category_id: Optional[int] = None
    summary: Optional[str] = None
    status: str = "in_progress"


def _row_to_profile(row: sqlite3.Row) -> BusinessProfile:
    return BusinessProfile(
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
        status=row["status"],
    )


def get_business_profile(conn: sqlite3.Connection, user_email: str) -> Optional[BusinessProfile]:
    row = conn.execute("SELECT * FROM business_profiles WHERE user_email = ?", (user_email,)).fetchone()
    return _row_to_profile(row) if row else None


def upsert_business_profile(conn: sqlite3.Connection, profile: BusinessProfile) -> None:
    """Fields left as None on `profile` overwrite whatever was stored --
    callers that only want to patch specific fields should load the
    existing profile first, update it, then pass the whole thing back in.
    Partial (not `status='complete'`) profiles are expected and fine:
    the Products page applies whatever defaults it can from whatever
    fields are actually populated -- see dashboard/queries.py callers."""
    values = {
        "user_email": profile.user_email,
        "seller_type": profile.seller_type,
        "product_niche": profile.product_niche,
        "target_market": profile.target_market,
        "sales_channels": json.dumps(profile.sales_channels),
        "marketing_approach": json.dumps(profile.marketing_approach),
        "budget_stage": profile.budget_stage,
        "experience_level": profile.experience_level,
        "primary_category_id": profile.primary_category_id,
        "summary": profile.summary,
        "status": profile.status,
    }
    set_clause = ",\n            ".join(f"{col}=excluded.{col}" for col in _FIELDS)
    conn.execute(
        f"""
        INSERT INTO business_profiles (
            user_email, {", ".join(_FIELDS)}, updated_at
        ) VALUES (
            :user_email, {", ".join(f":{col}" for col in _FIELDS)}, datetime('now')
        )
        ON CONFLICT(user_email) DO UPDATE SET
            {set_clause},
            updated_at=datetime('now')
        """,
        values,
    )
    conn.commit()


def delete_business_profile(conn: sqlite3.Connection, user_email: str) -> None:
    conn.execute("DELETE FROM business_profiles WHERE user_email = ?", (user_email,))
    conn.commit()
