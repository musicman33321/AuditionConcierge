"""Query helper for AuditionConcierge.

Structured filter FIRST, vector search second. The LLM step only ever
receives the records returned here, never the full store.
"""

from .heights import to_cm
from .store import cosine


def _deadline_of(role):
    value = role.get("deadline")
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    try:
        from datetime import datetime

        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def search_roles(store, *, height_in=None, equity=None, deadline_after=None,
                 query_text=None, embedder=None, limit=10):
    """Return active roles passing structured filters, vector-ranked.

    - height_in: only roles whose height range contains it; roles with
      no parsed height do not match a height query.
    - equity: "equity" or "non-equity", case-insensitive.
    - deadline_after: only roles with deadline >= it, or no deadline.
    - query_text + embedder: rank the filtered set by vector similarity.
      Without them, results are ordered by deadline, then title.
    """
    results = []
    for role in store.all_active():
        if height_in is not None:
            lo, hi = role.get("height_min_in"), role.get("height_max_in")
            # 0.5 in tolerance absorbs cm->inch rounding (162 cm = 63.8 in).
            if lo is None or hi is None or not (lo - 0.5 <= height_in <= hi + 0.5):
                continue
        if equity is not None:
            if (role.get("equity_status") or "").lower() != equity.lower():
                continue
        if deadline_after is not None:
            deadline = _deadline_of(role)
            if deadline is not None and deadline < deadline_after:
                continue
        results.append(role)
    if query_text is not None and embedder is not None:
        query_vec = embedder.embed(query_text)
        results.sort(
            key=lambda r: cosine(query_vec, r.get("embedding") or []), reverse=True
        )
    else:
        results.sort(key=lambda r: (str(r.get("deadline") or "9999"), r.get("title", "")))
    return results[:limit]


def format_height(role, unit="in"):
    lo, hi = role.get("height_min_in"), role.get("height_max_in")
    if lo is None or hi is None:
        return "N/A"
    if unit == "cm":
        return f"{to_cm(lo):g}-{to_cm(hi):g} cm"
    return f"{lo:g}-{hi:g} in"


def llm_context(records, unit="in"):
    """Format ONLY the given records for the LLM. No store access here."""
    lines = []
    for role in records:
        lines.append(
            f"Role: {role.get('role_name')} | Title: {role.get('title')} | "
            f"Height: {format_height(role, unit)} | "
            f"Equity: {role.get('equity_status') or 'unknown'} | "
            f"Deadline: {role.get('deadline') or 'unknown'} | "
            f"Location: {role.get('location')} | "
            f"Description: {(role.get('clean_text') or '')[:500]}"
        )
    return "\n".join(lines)
