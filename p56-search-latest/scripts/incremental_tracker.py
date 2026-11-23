"""Replayable incremental literature tracking over retained, dated snapshots.

No system clock or remote request is used.  A run requires explicit half-open
window bounds.  Registry processing dates are never rewritten as publication
 dates, and a failed source or ambiguous date prevents state/watermark commit.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

SCHEMA_VERSION = "latest-literature-tracker/v2"
DATE_FIELDS = {
    "online": ("published-online", "published_online", "online", "online_date"),
    "print": ("published-print", "published_print", "print", "print_date"),
    "issued": ("issued", "publication_date", "published", "pubDate", "firstPublicationDate"),
    "created": ("created",),
    "deposited": ("deposited",),
    "indexed": ("indexed", "firstIndexDate", "first_indexed_at"),
    "imported_at": ("imported_at", "first_seen_at", "snapshot_imported_at"),
}


def _text(value):
    return str(value).strip() if value is not None else ""


def _list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _doi(value):
    value = _text(value).lower()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value).rstrip(" .;")


def _title(value):
    value = unicodedata.normalize("NFKD", _text(value))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))


def _names(value):
    out = []
    for item in _list(value):
        if isinstance(item, dict):
            name = item.get("name") or item.get("display_name")
            if not name:
                family = _text(item.get("family") or item.get("lastName"))
                given = _text(item.get("given") or item.get("firstName"))
                name = (given + " " + family).strip() if given and family else family or given
        else:
            name = item
        if _text(name):
            out.append(_text(name))
    return out


def _author_keys(names):
    keys = set()
    for name in names:
        parts = _title(name).split()
        if not parts:
            continue
        if "," in name:
            rest = _title(name.split(",", 1)[1]).split()
            keys.add((_title(name.split(",", 1)[0]).replace(" ", ""), rest[0][0] if rest else ""))
        elif len(parts) == 1:
            keys.add((parts[0], ""))
        else:
            keys.add((parts[-1], parts[0][0]))
    return keys


def _year(record):
    for key in ("year", "publication_year", "pubYear"):
        if str(record.get(key) or "").isdigit():
            return int(record[key])
    for semantic, aliases in DATE_FIELDS.items():
        if semantic not in ("online", "print", "issued"):
            continue
        for key in aliases:
            if key in record:
                match = re.search(r"(?:19|20)\d{2}", _text(record[key]))
                if match:
                    return int(match.group())
    return None


def _tzinfo(name):
    offsets = {"UTC": 0, "Z": 0, "Asia/Shanghai": 8 * 60, "Europe/London": 0,
               "America/New_York": -5 * 60}
    if name in offsets:
        # Fixed fallbacks are intentional and disclosed where zoneinfo is unavailable.
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name), False
        except Exception:
            return timezone(timedelta(minutes=offsets[name])), name not in ("UTC", "Z")
    match = re.fullmatch(r"(?:UTC)?([+-])(\d{2}):?(\d{2})?", _text(name))
    if match:
        minutes = int(match.group(2)) * 60 + int(match.group(3) or 0)
        return timezone(timedelta(minutes=minutes if match.group(1) == "+" else -minutes)), False
    return timezone.utc, True


def _rfctime(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _advance_period(dt, precision):
    if precision == "year":
        return dt.replace(year=dt.year + 1)
    if precision == "month":
        return dt.replace(year=dt.year + (1 if dt.month == 12 else 0),
                          month=1 if dt.month == 12 else dt.month + 1)
    return dt + timedelta(days=1)


def _parse_date(value, tz_name="UTC"):
    """Return an instant plus its source precision and conservative interval end."""
    if value in (None, "", [], {}):
        return None
    original = value
    precision = "second"
    from_parts = False
    date_time, timestamp, parts = None, None, None
    if isinstance(value, dict):
        date_time = value.get("date-time") or value.get("date_time")
        timestamp = value.get("timestamp")
        parts = value.get("date-parts") or value.get("date_parts")
        if not date_time and timestamp is None and parts:
            value = parts
        elif date_time:
            value = date_time
        elif timestamp is not None:
            try:
                number = float(timestamp) / (1000 if abs(float(timestamp)) > 100000000000 else 1)
                dt = datetime.fromtimestamp(number, tz=timezone.utc)
                return {"instant": dt, "utc": _rfctime(dt), "raw": original,
                        "precision": "millisecond" if float(timestamp) > 100000000000 else "second",
                        "interval_end_utc": _rfctime(dt + timedelta(milliseconds=1)),
                        "timezone_assumed": False}
            except (TypeError, ValueError, OverflowError, OSError):
                return None
    if isinstance(value, list):
        from_parts = True
        parts = value[0] if len(value) == 1 and isinstance(value[0], list) else value
        try:
            numbers = [int(parts[i]) if i < len(parts) else 1 for i in range(3)]
            if not 1 <= numbers[1] <= 12 or not 1 <= numbers[2] <= calendar.monthrange(numbers[0], numbers[1])[1]:
                return None
        except (TypeError, ValueError, IndexError):
            return None
        precision = "year" if len(parts) == 1 else ("month" if len(parts) == 2 else "day")
        value = "%04d-%02d-%02d" % tuple(numbers)
    value = _text(value)
    if not from_parts and re.fullmatch(r"\d{4}", value):
        precision, value = "year", value + "-01-01"
    elif not from_parts and re.fullmatch(r"\d{4}-\d{2}", value):
        precision, value = "month", value + "-01"
    elif not from_parts and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        precision = "day"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    assumed = False
    if dt.tzinfo is None:
        zone, assumed = _tzinfo(tz_name)
        dt = dt.replace(tzinfo=zone)
    interval_end = _advance_period(dt, precision) if precision in ("year", "month", "day") else dt + timedelta(microseconds=1)
    return {"instant": dt, "utc": _rfctime(dt), "raw": original, "precision": precision,
            "interval_end_utc": _rfctime(interval_end), "timezone_assumed": assumed}


def _date_value(record, semantic):
    for key in DATE_FIELDS[semantic]:
        if key in record:
            return record[key]
    return None


def _status(record):
    status = _text(record.get("status") or record.get("publication_status")).lower()
    notice = _text(record.get("type") or record.get("publicationType")).lower()
    if record.get("retracted") is True or "retract" in status or "retract" in notice:
        return "retracted"
    if "correct" in status or "errat" in status or "correct" in notice or "errat" in notice:
        return "corrected"
    if "update" in status:
        return "updated"
    return status or "unchanged"


def _source_rows(spec):
    sources = spec.get("sources") if isinstance(spec.get("sources"), dict) else {}
    if sources:
        for source, payload in sources.items():
            payload = payload if isinstance(payload, dict) else {"status": "error", "records": []}
            for index, raw in enumerate(_list(payload.get("records") or payload.get("results"))):
                yield _text(source), payload, raw, index
    else:
        for index, raw in enumerate(_list(spec.get("records") or spec.get("documents"))):
            source = _text(raw.get("source") or raw.get("database") or "snapshot") if isinstance(raw, dict) else "unknown"
            yield source or "unknown", {}, raw, index


def _normalise(source, raw, index, tz_name):
    if not isinstance(raw, dict):
        return None, {"source": source, "index": index, "error": "record is not an object"}
    external = raw.get("externalIds") if isinstance(raw.get("externalIds"), dict) else {}
    rid = _text(raw.get("id") or raw.get("record_id") or raw.get("paperId") or raw.get("DOI")
                or raw.get("doi") or raw.get("title"))
    title = _text(raw.get("title") or raw.get("display_name") or raw.get("articleTitle"))
    if not rid and title:
        rid = "title:" + _title(title)
    if not rid and not title:
        return None, {"source": source, "index": index, "error": "record has no id or title"}
    authors = _names(raw.get("authors") or raw.get("author") or raw.get("creators"))
    clean = dict(raw)
    clean.update({
        "_source": source, "_rid": rid or "row-%06d" % index,
        "_observation": source + ":" + (rid or "row") + ":" + str(index),
        "_title": title, "_title_key": _title(title), "_doi": _doi(raw.get("doi") or raw.get("DOI")
                                                                    or external.get("DOI")),
        "_authors": authors, "_author_keys": _author_keys(authors), "_year": _year(raw),
        "_version_group": _text(raw.get("version_group") or raw.get("work_family")
                                 or raw.get("canonical_work_id")),
        "_status": _status(raw),
    })
    clean["_dates"] = {semantic: _parse_date(_date_value(raw, semantic), tz_name)
                       for semantic in DATE_FIELDS}
    clean["_invalid_dates"] = [semantic for semantic in DATE_FIELDS
                                if _date_value(raw, semantic) not in (None, "", [], {})
                                and clean["_dates"][semantic] is None]
    clean["_version_signature"] = _text(raw.get("version_id") or raw.get("version")
                                        or clean["_doi"] or clean["_rid"])
    clean["_content_fingerprint"] = hashlib.sha256(json.dumps(
        {"title": title, "version": clean["_version_signature"], "status": clean["_status"],
         "raw": {k: v for k, v in raw.items() if k in ("relation", "update_to", "updated_by")}},
        sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
    return clean, None


class _Sets:
    def __init__(self, rows):
        self.parent = {r["_observation"]: r["_observation"] for r in rows}

    def find(self, key):
        if self.parent[key] != key:
            self.parent[key] = self.find(self.parent[key])
        return self.parent[key]

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        a, b = sorted((a, b))
        self.parent[b] = a


def _identity(rows):
    sets = _Sets(rows)
    evidence = []
    def link(group, rule, value):
        for other in group[1:]:
            if sets.find(group[0]["_observation"]) != sets.find(other["_observation"]):
                sets.union(group[0]["_observation"], other["_observation"])
                evidence.append({"left": group[0]["_observation"], "right": other["_observation"],
                                 "rule": rule, "evidence": value, "merged": True})
    by_doi, by_version = {}, {}
    for row in rows:
        if row["_doi"]:
            by_doi.setdefault(row["_doi"], []).append(row)
        if row["_version_group"]:
            by_version.setdefault(row["_version_group"], []).append(row)
    for value, group in sorted(by_doi.items()):
        link(group, "doi_exact", value)
    for value, group in sorted(by_version.items()):
        link(group, "declared_version_group", value)
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if sets.find(a["_observation"]) == sets.find(b["_observation"]):
                continue
            explicit = bool(a["_version_group"] and a["_version_group"] == b["_version_group"])
            if a["_doi"] and b["_doi"] and a["_doi"] != b["_doi"] and not explicit:
                continue
            if a["_year"] and b["_year"] and abs(a["_year"] - b["_year"]) > 1:
                continue
            if not a["_title_key"] or not b["_title_key"]:
                continue
            ratio = SequenceMatcher(None, a["_title_key"], b["_title_key"]).ratio()
            shared = a["_author_keys"] & b["_author_keys"]
            creator_free = not a["_authors"] and not b["_authors"]
            exact = a["_title_key"] == b["_title_key"]
            if not ((exact and (shared or creator_free or explicit)) or (ratio >= 0.94 and shared)):
                continue
            ar, br = sets.find(a["_observation"]), sets.find(b["_observation"])
            left = [r for r in rows if sets.find(r["_observation"]) == ar]
            right = [r for r in rows if sets.find(r["_observation"]) == br]
            if not explicit and any(x["_doi"] and y["_doi"] and x["_doi"] != y["_doi"]
                                    for x in left for y in right):
                continue
            sets.union(a["_observation"], b["_observation"])
            evidence.append({"left": a["_observation"], "right": b["_observation"],
                             "rule": "title_exact_author" if exact else "title_fuzzy_author",
                             "title_similarity": round(ratio, 6), "shared_creators": sorted(shared),
                             "merged": True})
    groups = {}
    for row in rows:
        groups.setdefault(sets.find(row["_observation"]), []).append(row)
    return groups, evidence


def _stable_key(members):
    family = sorted({m["_version_group"] for m in members if m["_version_group"]})
    if family:
        return "family:" + family[0]
    published = sorted({m["_doi"] for m in members if m["_doi"] and not m["_doi"].startswith("10.48550/")})
    if published:
        return "doi:" + published[0]
    dois = sorted({m["_doi"] for m in members if m["_doi"]})
    if dois:
        return "doi:" + dois[0]
    rep = sorted(members, key=lambda r: r["_observation"])[0]
    return "title:" + rep["_title_key"] + "|author:" + "&".join(
        sorted(a + ":" + b for a, b in rep["_author_keys"]))


def _version_records(members):
    return sorted([{"signature": m["_version_signature"], "version": m.get("version"),
                    "source": m["_source"], "record_id": m["_rid"], "doi": m["_doi"] or None,
                    "fingerprint": m["_content_fingerprint"]} for m in members],
                  key=lambda v: (v["signature"], v["source"], v["record_id"]))


def _state_work(members):
    rep = sorted(members, key=lambda m: (m["_doi"].startswith("10.48550/"), not bool(m["_doi"]),
                                         m["_source"], m["_observation"]))[0]
    return {"work_key": _stable_key(members), "title": rep["_title"] or None,
            "doi": rep["_doi"] or None, "year": rep["_year"],
            "version_records": _version_records(members),
            "status": sorted({m["_status"] for m in members}),
            "aliases": sorted({a for m in members for a in (m["_rid"], m["_doi"], m["_title_key"]) if a})}


def _previous(spec):
    raw = spec.get("previous_state") or spec.get("previousSnapshot") or spec.get("previous_snapshot") or {}
    if isinstance(raw, list):
        raw = {"works_raw": raw}
    if not isinstance(raw, dict):
        raw = {}
    works = {}
    for item in _list(raw.get("works") or raw.get("seen_works")):
        if isinstance(item, dict) and _text(item.get("work_key")):
            works[_text(item["work_key"])] = item
    # Raw old exports are accepted as a cold-import bridge and deduplicated by same rules.
    old_raw = raw.get("works_raw")
    if old_raw is None and isinstance(spec.get("previous_snapshot"), list):
        old_raw = spec["previous_snapshot"]
    if old_raw:
        old_rows, _ = [], []
        for index, record in enumerate(_list(old_raw)):
            if isinstance(record, dict):
                clean, bad = _normalise(_text(record.get("source") or "previous"), record, index,
                                        _text(spec.get("timezone") or "UTC"))
                if clean:
                    old_rows.append(clean)
        groups, _ = _identity(old_rows)
        for members in groups.values():
            work = _state_work(members)
            works[work["work_key"]] = work
    return {"watermark": raw.get("watermark") or raw.get("last_window_end"),
            "works": works, "notifications": _list(raw.get("notifications") or raw.get("deliveries")),
            "read_works": sorted({_text(x) for x in _list(raw.get("read_works")) if _text(x)}),
            "tracked_works": sorted({_text(x) for x in _list(raw.get("tracked_works")) if _text(x)})}


def _choose_events(members, spec, payload_by_source):
    global_fields = [_text(x) for x in _list(spec.get("tracking_date_fields"))]
    configured = _text(spec.get("tracking_date_field"))
    events, missing = [], []
    for member in members:
        fields = global_fields or ([configured] if configured else [])
        if not fields:
            source_policy = _text(payload_by_source.get(member["_source"], {}).get("tracking_date_field"))
            fields = [source_policy] if source_policy else ["imported_at", "indexed"]
        chosen = next((field for field in fields if field in DATE_FIELDS and member["_dates"].get(field)), None)
        if chosen:
            events.append((member, chosen, member["_dates"][chosen]))
        else:
            missing.append(member)
    return events, missing


def _relation(date, start, end):
    instant = date["instant"]
    interval_end = datetime.fromisoformat(date["interval_end_utc"].replace("Z", "+00:00"))
    if instant < start:
        return "overlaps_start" if interval_end > start else "before"
    if instant >= end:
        return "after"
    return "overlaps_end" if interval_end > end else "inside"


def _date_export(members):
    return [{"source": m["_source"], "record_id": m["_rid"],
             "dates": {semantic: ({k: v for k, v in parsed.items() if k != "instant"} if parsed else None)
                       for semantic, parsed in m["_dates"].items()},
             "invalid_dates": m["_invalid_dates"]} for m in sorted(members, key=lambda r: r["_observation"])]


def _notification_id(work_key, start, kind, versions):
    raw = work_key + "|" + _rfctime(start) + "|" + kind + "|" + ",".join(versions)
    return "notice-" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def run(spec):
    tz_name = _text((spec.get("window") or {}).get("timezone") if isinstance(spec.get("window"), dict)
                    else spec.get("timezone")) or _text(spec.get("timezone") or "UTC")
    window = spec.get("window") if isinstance(spec.get("window"), dict) else {}
    previous = _previous(spec)
    start_raw = window.get("start") or spec.get("window_start") or previous["watermark"]
    end_raw = window.get("end") or spec.get("window_end")
    start, end = _parse_date(start_raw, tz_name), _parse_date(end_raw, tz_name)
    if not start or not end or end["instant"] <= start["instant"]:
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "tracker.window_incomplete",
                            "message": "explicit valid window start/end are required; system time is never inferred"},
                "limits": ["no increment was computed", "watermark was not advanced"]}
    start_dt, end_dt = start["instant"], end["instant"]
    subscription = spec.get("subscription") if isinstance(spec.get("subscription"), dict) else {}
    sources = spec.get("sources") if isinstance(spec.get("sources"), dict) else {}
    required = [_text(s) for s in _list(spec.get("required_sources") or subscription.get("sources"))]
    if not required:
        required = sorted(sources) or sorted({s for s, _, _, _ in _source_rows(spec)})
    rejected, rows, invalid = [], [], []
    payload_by_source = {}
    source_counts = {s: {"records_seen": 0, "records_valid": 0, "records_rejected": 0} for s in required}
    for source, payload, raw, index in _source_rows(spec):
        payload_by_source[source] = payload
        source_counts.setdefault(source, {"records_seen": 0, "records_valid": 0, "records_rejected": 0})
        source_counts[source]["records_seen"] += 1
        clean, bad = _normalise(source, raw, index, tz_name)
        if bad:
            rejected.append(bad)
            source_counts[source]["records_rejected"] += 1
            continue
        clean["_tracking_field"] = payload.get("tracking_date_field")
        source_counts[source]["records_valid"] += 1
        rows.append(clean)
        invalid.extend(clean for _ in [0] if clean["_invalid_dates"])
    if not required and not rows and not rejected:
        return {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                "refusal": {"rule": "tracker.no_sources", "message": "no source snapshots were supplied"},
                "limits": ["watermark was not advanced"]}
    groups, identity_evidence = _identity(rows)
    previous_works = previous["works"]
    buckets = {"new_works": [], "late_arrivals": [], "version_updates": [],
               "status_updates": [], "unchanged": [], "out_of_window": [], "review_required": []}
    ad_hoc = []
    for _, members in sorted(groups.items(), key=lambda item: _stable_key(item[1])):
        members.sort(key=lambda r: r["_observation"])
        work = _state_work(members)
        events, undated = _choose_events(members, spec, payload_by_source)
        boundary = []
        in_window = []
        for member, field, parsed in events:
            relation = _relation(parsed, start_dt, end_dt)
            item = {"record_id": member["_rid"], "source": member["_source"],
                    "tracking_date_field": field, "event_utc": parsed["utc"],
                    "event_precision": parsed["precision"], "window_relation": relation}
            ad_hoc.append(dict(item, work_key=work["work_key"]))
            if relation == "inside":
                in_window.append((member, field, parsed))
            elif relation.startswith("overlaps"):
                boundary.append(item)
        publication_dates = [m["_dates"]["online"] or m["_dates"]["issued"] for m in members]
        publication_dates = [d for d in publication_dates if d]
        old = previous_works.get(work["work_key"])
        current_versions = {v["signature"] for v in work["version_records"]}
        prior_versions = {v.get("signature") for v in _list(old.get("version_records")) if isinstance(v, dict)} if old else set()
        new_versions = sorted(current_versions - prior_versions) if old else []
        current_status = set(work["status"])
        old_status = set(_list(old.get("status"))) if old else set()
        status_changed = bool(current_status - old_status)
        base = dict(work, sources=sorted({m["_source"] for m in members}),
                    source_records=[{"source": m["_source"], "record_id": m["_rid"],
                                     "observation_id": m["_observation"]} for m in members],
                    date_interpretations=_date_export(members),
                    in_window_events=[{"source": m["_source"], "record_id": m["_rid"],
                                       "tracking_date_field": f, "event_utc": d["utc"]}
                                      for m, f, d in in_window],
                    new_versions=new_versions, deduplication_key=work["work_key"])
        if invalid and any(m in invalid for m in members) or undated or boundary:
            reasons = []
            if undated:
                reasons.append("missing configured discovery date on " + ",".join(m["_rid"] for m in undated))
            if any(m in invalid for m in members):
                reasons.append("invalid source date")
            if boundary:
                reasons.append("imprecise event interval overlaps a window boundary")
            buckets["review_required"].append(dict(base, review_reasons=reasons))
            continue
        if old:
            if new_versions and in_window and current_status != {"retracted"}:
                buckets["version_updates"].append(dict(base, update_kind="new_version",
                    reason="same work family has a new version signature in this window"))
            elif status_changed and in_window:
                buckets["status_updates"].append(dict(base, update_kind="status_change",
                    previous_status=sorted(old_status), reason="retraction/correction/status is an update, not a new work"))
            else:
                buckets["unchanged"].append(dict(base, suppression_reason="work/version already present in previous snapshot"))
            continue
        if not in_window:
            buckets["out_of_window"].append(dict(base, suppression_reason="no selected discovery event inside [start,end)"))
            continue
        if current_status & {"retracted", "corrected"}:
            buckets["status_updates"].append(dict(base, update_kind="new_status_notice",
                previous_status=[], reason="notice/update record classified separately from a newly published work"))
            continue
        late = False
        lag = None
        if publication_dates:
            event_date = min(in_window, key=lambda x: x[2]["instant"])[2]
            # Use the earliest declared online/issued date for delay reporting.
            published = min(publication_dates, key=lambda d: d["instant"])
            late = published["instant"] < start_dt
            lag = (event_date["instant"].date() - published["instant"].date()).days
        if late:
            buckets["late_arrivals"].append(dict(base, novelty_kind="late_indexed_old_work",
                publication_lag_days=lag, reason="old publication/new source observation; not labelled as a new publication"))
        else:
            buckets["new_works"].append(dict(base, novelty_kind="new_to_snapshot" if publication_dates else "new_to_snapshot_publication_date_missing",
                publication_lag_days=lag if lag is not None and lag >= 0 else None,
                reason="first appearance relative to previous snapshot and explicit window"))
    # A paused subscription produces no delivery plan and no state transition.
    paused = bool(subscription.get("paused") or spec.get("paused"))
    read = set(previous["read_works"]) | {_text(x) for x in _list(subscription.get("read_works")) if _text(x)}
    tracked = set(previous["tracked_works"]) | {_text(x) for x in _list(subscription.get("tracked_works")) if _text(x)}
    suppressed, reminders = [], []
    if paused:
        for kind in ("new_works", "late_arrivals", "version_updates", "status_updates"):
            for work in buckets[kind]:
                reminders.append({"notification_id": _notification_id(work["work_key"], start_dt, kind, work["new_versions"]),
                                  "work_key": work["work_key"], "kind": kind, "title": work["title"],
                                  "delivery_status": "suppressed_paused"})
                suppressed.append({"work_key": work["work_key"], "reason": "subscription paused"})
    else:
        for kind in ("new_works", "late_arrivals", "version_updates", "status_updates"):
            for work in buckets[kind]:
                notice_id = _notification_id(work["work_key"], start_dt, kind, work["new_versions"])
                if work["work_key"] in read and not subscription.get("notify_read", False):
                    suppressed.append({"work_key": work["work_key"], "notification_id": notice_id,
                                       "reason": "already read"})
                    continue
                if tracked and work["work_key"] not in tracked:
                    suppressed.append({"work_key": work["work_key"], "notification_id": notice_id,
                                       "reason": "work not in tracked set"})
                    continue
                reminders.append({"notification_id": notice_id, "work_key": work["work_key"],
                                  "kind": kind, "title": work["title"], "doi": work["doi"],
                                  "evidence": work["in_window_events"],
                                  "publication_lag_days": work.get("publication_lag_days"),
                                  "new_versions": work["new_versions"],
                                  "read": work["work_key"] in read,
                                  "tracking": work["work_key"] in tracked if tracked else "subscription_default",
                                  "delivery_status": "prepared_not_sent"})
    source_summary = []
    incomplete, empty_ok = [], []
    for source in required:
        payload = sources.get(source) if isinstance(sources.get(source), dict) else {}
        status = payload.get("status") or ("ok" if source in {r["_source"] for r in rows} else "missing")
        counts = source_counts.get(source, {"records_seen": 0, "records_valid": 0, "records_rejected": 0})
        source_summary.append({"source": source, "status": status, "error": payload.get("error"),
                               "snapshot_ref": payload.get("snapshot_ref"), "retrieval_window": payload.get("retrieval_window"),
                               **counts})
        if status not in ("ok", "success", "complete"):
            incomplete.append(source)
        elif counts["records_valid"] == 0:
            empty_ok.append(source)
    prior_watermark = _parse_date(previous["watermark"], tz_name) if previous["watermark"] else None
    discontinuity = bool(prior_watermark and prior_watermark["instant"] != start_dt)
    commit = not incomplete and not rejected and not buckets["review_required"] and not discontinuity and not paused
    # Do not commit provisional findings on a failed/ambiguous window; this is what
    # makes retry capable of recovering missed reports without duplicate delivery.
    all_work_states = {}
    if commit:
        all_work_states.update(previous_works)
        for members in groups.values():
            work = _state_work(members)
            old = all_work_states.get(work["work_key"])
            if old:
                versions = {(v.get("signature"), v.get("source"), v.get("record_id")): v
                            for v in _list(old.get("version_records")) if isinstance(v, dict)}
                for version in work["version_records"]:
                    versions[(version["signature"], version["source"], version["record_id"])] = version
                work["version_records"] = sorted(versions.values(), key=lambda v: (
                    _text(v.get("signature")), _text(v.get("source")), _text(v.get("record_id"))))
                work["status"] = sorted(set(_list(old.get("status"))) | set(work["status"]))
                work["aliases"] = sorted(set(_list(old.get("aliases"))) | set(work["aliases"]))
            all_work_states[work["work_key"]] = work
    else:
        all_work_states.update(previous_works)
    next_state = {"schema_version": "latest-tracker-state/v2",
                  "watermark": end["utc"] if commit else (previous["watermark"] or start["utc"]),
                  "works": [all_work_states[k] for k in sorted(all_work_states)],
                  "notifications": previous["notifications"] + [dict(n, delivery_status="prepared_not_sent")
                          for n in reminders if n["delivery_status"] == "prepared_not_sent"] if commit else previous["notifications"],
                  "read_works": sorted(read), "tracked_works": sorted(tracked)}
    findings = []
    limits = ["Reminders are local prepared records; no scheduler, network delivery, or current-time claim is made"]
    if incomplete:
        findings.append({"rule": "tracker.source_incomplete", "severity": "high", "sources": incomplete})
        limits.append("incomplete sources can cause missed reports; watermark was held")
    if empty_ok:
        findings.append({"rule": "tracker.empty_source_window", "severity": "low", "sources": empty_ok})
    if rejected:
        findings.append({"rule": "tracker.record_rejected", "severity": "high", "entries": rejected})
        limits.append("malformed records prevented safe state commit")
    if buckets["review_required"]:
        findings.append({"rule": "tracker.date_unresolved", "severity": "high",
                         "count": len(buckets["review_required"])})
        limits.append("missing/invalid/boundary-ambiguous dates prevented safe state commit")
    if discontinuity:
        findings.append({"rule": "tracker.window_discontinuity", "severity": "high",
                         "previous_watermark": previous["watermark"], "requested_start": start["utc"]})
        limits.append("previous watermark does not equal requested start; overlap/gap was not silently repaired")
    if paused:
        findings.append({"rule": "tracker.subscription_paused", "severity": "low"})
        limits.append("paused subscription did not commit a new window")
    total_valid = len(rows)
    review_count = len(buckets["review_required"])
    other_count = sum(len(v) for k, v in buckets.items() if k != "review_required")
    reconciliation = {
        "records_seen": sum(c["records_seen"] for c in source_counts.values()),
        "records_valid": total_valid, "records_rejected": len(rejected),
        "identity_clusters": len(groups), "collapsed_observations": total_valid - len(groups),
        "classified_clusters": review_count + other_count,
        "category_counts": {k: len(v) for k, v in buckets.items()},
        "reminders_prepared": sum(n["delivery_status"] == "prepared_not_sent" for n in reminders),
        "reminders_suppressed": len(suppressed),
    }
    reconciliation["closed"] = reconciliation["records_seen"] == total_valid + len(rejected) and \
        reconciliation["identity_clusters"] == reconciliation["classified_clusters"]
    fingerprint = hashlib.sha256(json.dumps({"sources": sources, "window": {
        "start": start["utc"], "end": end["utc"]}, "previous": previous,
        "date_fields": spec.get("tracking_date_fields") or spec.get("tracking_date_field")},
        sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    status = "review" if any(f["severity"] == "high" for f in findings) else "clean"
    return {
        "schema_version": SCHEMA_VERSION, "status": status, "ok": True,
        "subscription": {"sources": required, "paused": paused, "timezone": tz_name,
                         "tracking_date_fields": spec.get("tracking_date_fields")
                         or spec.get("tracking_date_field") or ["imported_at", "indexed"]},
        "current_window": {"start": start["utc"], "end": end["utc"], "start_inclusive": True,
                           "end_exclusive": True, "timezone": tz_name,
                           "previous_watermark": previous["watermark"], "continuous": not discontinuity},
        **buckets, "new_items": buckets["new_works"] + buckets["late_arrivals"],
        "reminders": reminders, "suppressed": suppressed,
        "delivery_log": [{"notification_id": n["notification_id"], "status": n["delivery_status"]} for n in reminders],
        "date_interpretations": ad_hoc,
        "source_status": source_summary, "identity_merges": identity_evidence,
        "missed_reporting_risk": {"sources_incomplete": incomplete,
                                  "records_requiring_date_review": review_count,
                                  "watermark_held": not commit,
                                  "retry_required": not commit},
        "count_reconciliation": reconciliation,
        "next_watermark": next_state["watermark"], "state_committed": commit,
        "next_state": next_state, "rejected_records": rejected,
        "findings": findings, "limits": limits,
        "uncertainty": "'New' means relative to the supplied previous snapshot and selected source event, not global novelty. Processing dates are not publication dates.",
        "change_log": [{"action": "window_evaluated", "start": start["utc"], "end": end["utc"]},
                       {"action": "state_commit", "committed": commit},
                       {"action": "reminder_preparation", "count": len(reminders)}],
        "snapshot_sha256": fingerprint,
    }


def is_tracker_spec(spec):
    return isinstance(spec, dict) and (spec.get("mode") in ("latest", "tracking", "incremental") or
        "previous_state" in spec or "previous_snapshot" in spec or "window_start" in spec)
