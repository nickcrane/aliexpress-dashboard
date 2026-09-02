"""Helpers for reading fields off either shape a response can arrive in:

- live mode: `types.SimpleNamespace` objects, built by the library's
  `json.loads(..., object_hook=SimpleNamespace)` in `aliexpress_api.helpers.requests`.
- fixture mode: plain dicts, loaded straight from our recorded JSON fixtures.

Reading through `get_field` lets the rest of the client and the normalizer stay
agnostic to which mode produced the data, so both modes run identical code from
here on.
"""

from __future__ import annotations

from typing import Any, Mapping


def get_field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def as_dict(obj: Any) -> dict:
    if isinstance(obj, Mapping):
        return dict(obj)
    return dict(vars(obj))


def extract_list(value: Any) -> list:
    """Several confirmed-live ds.* response fields that "should" be a bare
    array (per the docs) actually arrive one level deeper, wrapped in a
    single-key object -- `data.products` as `{"selection_search_product": [...]}`,
    `ae_item_sku_info_dtos` as `{"ae_item_sku_info_d_t_o": [...]}`,
    `ae_video_dtos` as `{"ae_video_d_t_o": [...]}`. The exact inner key
    varies (and may vary further by call type in ways this hasn't been able
    to confirm), so this takes the first list-valued entry found rather than
    hardcoding each one.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, Mapping):
        for inner in value.values():
            if isinstance(inner, list):
                return inner
    return []
