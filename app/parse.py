"""Parsing for AuditionConcierge, extracted from disneyauditionsearch.ipynb.

The notebook's feed logic is preserved here without the notebook's
Gemini/Kaggle dependencies:
- fetch the XML feed, one <audition> element per posting
- clean the HTML in <notes> into readable text
- split one posting into role records when it lists several roles

Deadline rule: the feed has no explicit deadline field, so the audition
date (start_date) is used as the deadline proxy. A posting may also carry
an explicit "deadline" field, or a "Deadline:" / "Due:" line in its text,
and that wins when present.
"""

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import date

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - bs4 is optional here
    BeautifulSoup = None

from .heights import parse_height_range

FEED_URL = "https://services2.tmpwebeng.com/feed/disney-event-feed-proxy.aspx"

_FIELD_LABELS = {
    "height", "equity", "location", "date", "deadline", "description",
    "requirements", "notes", "audition", "apply", "about",
}


def clean_html_description(html_text: str) -> str:
    """Clean HTML from a job description, as in the notebook."""
    if not html_text:
        return ""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_text, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator="\n")
    else:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "\n", text)
        text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _text(element, tag: str) -> str:
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def parse_feed_xml(xml_text: str):
    """Parse the Disney feed XML into posting dicts (notebook fields)."""
    root = ET.fromstring(xml_text)
    postings = []
    for aud in root.iter("audition"):
        notes = _text(aud, "notes")
        postings.append({
            "audition_id": aud.get("id", ""),
            "name": _text(aud, "name"),
            "park_location": _text(aud, "businessunit"),
            "city": _text(aud, "city"),
            "state": _text(aud, "state"),
            "venue": _text(aud, "venue"),
            "talent_type": _text(aud, "talent_type"),
            "audition_date": _text(aud, "start_date"),
            "audition_time": _text(aud, "start_time"),
            "timezone": _text(aud, "time_zone"),
            "job_description": clean_html_description(notes),
            "raw_notes": notes,
        })
    return postings


def fetch_disney_auditions(url: str = FEED_URL, timeout: int = 30):
    """Fetch the live feed. Uses urllib only, so no extra dependency."""
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as response:
        return parse_feed_xml(response.read().decode("utf-8", errors="replace"))


def _parse_date(value: str):
    """Parse YYYY-MM-DD or MM/DD/YYYY into a date, or None."""
    if not value:
        return None
    value = value.strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _find_deadline(text: str, posting: dict):
    if posting.get("deadline"):
        parsed = _parse_date(posting["deadline"])
        if parsed:
            return parsed
    m = re.search(r"(?:Deadline|Due|Apply by)\s*:?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    if m:
        return _parse_date(m.group(1))
    return _parse_date(posting.get("audition_date", ""))


def _detect_equity(text: str):
    lowered = text.lower()
    if "non-equity" in lowered or "non equity" in lowered or "non-union" in lowered:
        return "non-equity"
    if "equity" in lowered or re.search(r"\bAEA\b", text):
        return "equity"
    return None


def _detect_presentation(text: str):
    lowered = text.lower()
    if "female-presenting" in lowered or "female presenting" in lowered:
        return "female-presenting"
    if "male-presenting" in lowered or "male presenting" in lowered:
        return "male-presenting"
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "role"


def split_roles(clean_text: str, posting_name: str):
    """Split cleaned posting text into (role_name, section_text) pairs.

    Headings are lines like "Role: Mickey Mouse" or "Mickey Mouse:".
    Field labels (Height:, Equity:, ...) are not treated as roles.
    With no headings, the whole posting is one role named after it.
    """
    lines = clean_text.splitlines()
    sections = []
    current_name = None
    current_lines = []
    preamble = []
    for line in lines:
        m = re.match(r"^(?:Role|Character|Performer)\s*:\s*(.+?)\s*$", line)
        if not m:
            m = re.match(r"^([A-Z][A-Za-z0-9 &'\-]{2,40})\s*:\s*(.*)$", line)
        if m:
            heading = m.group(1).strip()
            rest = m.group(2).strip() if len(m.groups()) > 1 else ""
            if heading.lower() in _FIELD_LABELS:
                if current_name is not None:
                    current_lines.append(line)
                else:
                    current_lines.append(line)
                continue
            if current_name is not None:
                sections.append((current_name, "\n".join(current_lines).strip()))
            else:
                preamble = list(current_lines)
            current_name = heading
            current_lines = [rest] if rest else []
        else:
            current_lines.append(line)
    if current_name is not None:
        sections.append((current_name, "\n".join(current_lines).strip()))
    if not sections:
        return [(posting_name or "Role", clean_text)]
    if preamble:
        first_name, first_text = sections[0]
        sections[0] = (first_name, ("\n".join(preamble) + "\n" + first_text).strip())
    return sections


def _field_hash(fields: dict) -> str:
    payload = json.dumps(fields, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_posting(posting: dict):
    """Turn one feed posting into role records (see docs/data-storage-draft.md)."""
    posting_id = posting.get("audition_id") or _slug(
        f"{posting.get('name', '')}-{posting.get('audition_date', '')}"
    )
    clean_text = posting.get("job_description") or clean_html_description(
        posting.get("raw_notes", "")
    )
    location_parts = [p for p in (posting.get("city"), posting.get("state")) if p]
    location = ", ".join(location_parts) or posting.get("park_location", "")
    roles = []
    for role_name, section in split_roles(clean_text, posting.get("name", "")):
        height_min, height_max = parse_height_range(section)
        # A section may name a role but put its height in the posting header.
        if height_min is None and len(split_roles(clean_text, posting.get("name", ""))) == 1:
            height_min, height_max = parse_height_range(clean_text)
        equity = _detect_equity(section) or _detect_equity(clean_text)
        presentation = _detect_presentation(section) or _detect_presentation(clean_text)
        deadline = _find_deadline(section, posting)
        fields = {
            "title": posting.get("name", ""),
            "role_name": role_name,
            "location": location,
            "audition_date": posting.get("audition_date", ""),
            "deadline": str(deadline) if deadline else None,
            "height_min_in": height_min,
            "height_max_in": height_max,
            "performer_presentation": presentation,
            "equity_status": equity,
            "source_url": posting.get("source_url", ""),
            "clean_text": section,
        }
        if height_min is not None and deadline:
            confidence = "high"
        elif height_min is not None or deadline:
            confidence = "medium"
        else:
            confidence = "low"
        roles.append({
            "posting_id": posting_id,
            "role_id": f"{posting_id}-role-{_slug(role_name)}",
            "parse_confidence": confidence,
            "field_hash": _field_hash(fields),
            "raw_text": clean_text,
            "first_seen": None,
            "last_seen": None,
            "status": "active",
            **fields,
        })
    return roles
