"""Scientific context, explicit legend bindings and value-level uncertainty.

This module deliberately does not interpret prose.  It binds readings to the
caller-declared figure context and compares declared numeric claims with the
appropriate interval.  Semantic/causal interpretation remains the agent's job.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import calibrate as C


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _round(value):
    return round(float(value), 8) if _finite(value) else None


def interval(px, fit, delta_px):
    """Return an asymmetric reading interval by mapping both pixel endpoints.

    The interval describes raster-reading uncertainty, not a confidence interval
    and not the underlying experiment's error bar.  Log axes therefore keep
    their multiplicative/asymmetric form instead of receiving a fake +/- value.
    """
    if not fit.get("ok") or not _finite(px):
        return {"estimate": None, "lower": None, "upper": None,
                "unit": "axis_fraction", "basis": "uncalibrated axis"}
    estimate = float(C.px_to_value(px, fit))
    a = float(C.px_to_value(px - delta_px, fit))
    b = float(C.px_to_value(px + delta_px, fit))
    return {"estimate": _round(estimate), "lower": _round(min(a, b)),
            "upper": _round(max(a, b)), "pixel_center": _round(px),
            "pixel_half_width": _round(delta_px), "unit": fit.get("unit"),
            "kind": "raster_reading_interval_not_statistical_ci",
            "basis": "map both pixel endpoints through the fitted %s axis" % fit.get("scale", "unknown")}


def _axis_delta(fit, stroke_px=0.5):
    rms = fit.get("rms_px")
    # A frame-limit calibration has no residual.  Two pixels is a stated floor,
    # not evidence that the frame-to-data mapping is accurate.
    base = float(rms) if _finite(rms) else 2.0
    return max(0.5, base + max(0.5, float(stroke_px)))


def _stroke_half(series):
    basis = series.get("uncertainty_basis") or ""
    # Prefer measured thickness when it was retained by the digitiser.
    thick = series.get("median_stroke_thickness_px")
    return float(thick) / 2.0 if _finite(thick) else 0.75


def attach_intervals(result):
    """Add one auditable reading record per recovered point/bar."""
    readings = []
    for panel in result.get("panels", []):
        cal = panel.get("calibration") or {}
        fx, fy = cal.get("x") or {}, cal.get("y") or {}
        calibrated = bool(fx.get("ok") and fy.get("ok"))
        for series in panel.get("series", []):
            if not calibrated:
                series["value_status"] = "axis_fraction_estimate"
                continue
            series["value_status"] = "estimated_from_raster_not_exact"
            sid = series.get("series_index")
            points = ((series.get("evidence") or {}).get("points_px") or [])
            if series.get("chart_type") == "curve":
                intervals = []
                for i, point in enumerate(points):
                    if not isinstance(point, (list, tuple)) or len(point) != 2:
                        continue
                    xpx, ypx = point
                    xi = interval(xpx, fx, _axis_delta(fx))
                    yi = interval(ypx, fy, _axis_delta(fy, _stroke_half(series)))
                    row = {"image": panel.get("image"), "panel_id": panel.get("panel_id"),
                           "series_index": sid, "series_label": series.get("series_label"),
                           "point_index": i, "x": xi, "y": yi,
                           "x_unit": series.get("x_unit"), "y_unit": series.get("y_unit"),
                           "reading_tier": "calibrated_digitised",
                           "value_status": "estimated_from_raster_not_exact"}
                    intervals.append({"point_index": i, "x": xi, "y": yi})
                    readings.append(row)
                series["reading_intervals"] = intervals
                series["uncertainty_note"] = (
                    "estimate and interval are raster-reading quantities; neither is an exact source datum nor an experimental error bar")
            elif series.get("chart_type") == "bar":
                intervals = []
                for i, bar in enumerate(series.get("bars", [])):
                    xpx = bar.get("x_center_px")
                    yi = interval(bar.get("top_px"), fy, _axis_delta(fy, 0.5))
                    xi = interval(xpx, fx, _axis_delta(fx))
                    bi = {"bar_index": i, "x": xi, "top": yi,
                          "baseline_value": bar.get("baseline_value"),
                          "height_value": bar.get("height_value")}
                    intervals.append(bi)
                    readings.append({"image": panel.get("image"), "panel_id": panel.get("panel_id"),
                                     "series_index": sid, "series_label": series.get("series_label"),
                                     "bar_index": i, "x": xi, "y": yi,
                                     "x_unit": fx.get("unit"), "y_unit": fy.get("unit"),
                                     "reading_tier": "calibrated_digitised",
                                     "value_status": "estimated_from_raster_not_exact"})
                series["reading_intervals"] = intervals
                series["uncertainty_note"] = (
                    "bar-top intervals quantify raster reading only; annotations remain unconfirmed candidates")
    return readings


def bind_context(case, result):
    """Attach caller-read caption/text metadata and explicit legend mappings.

    A legend label is assigned only by a declared series_index or hue-bin match
    (or the explicitly allowed one-series/one-label case).  List order alone is
    never treated as identity.
    """
    by_image = {}
    for panel in result.get("panels", []):
        by_image.setdefault(panel.get("image"), []).append(panel)
    metadata = []
    raw_images = case.get("images") or case.get("figures") or []
    if isinstance(raw_images, str):
        raw_images = [raw_images]
    for raw in raw_images:
        spec = {"path": raw} if isinstance(raw, str) else raw
        if not isinstance(spec, dict):
            continue
        path = spec.get("resolved_path")
        entries = spec.get("legend_entries") or []
        if not isinstance(entries, list):
            entries = []
        for panel in by_image.get(path, []):
            for series in panel.get("series", []):
                series["series_label"] = None
                series["legend_binding"] = "unresolved"
                for entry in entries:
                    if not isinstance(entry, dict) or not entry.get("label"):
                        continue
                    matched = (entry.get("series_index") == series.get("series_index") or
                               (entry.get("hue_bin") is not None and
                                entry.get("hue_bin") == (series.get("appearance") or {}).get("hue_bin")))
                    if matched:
                        series["series_label"] = str(entry["label"])
                        series["legend_binding"] = "declared_series_index" if entry.get("series_index") is not None else "declared_hue_bin"
                        series["legend_evidence"] = {k: entry.get(k) for k in ("label", "series_index", "hue_bin", "locator") if k in entry}
                        break
                if (series["series_label"] is None and len(entries) == 1 and
                        len(panel.get("series", [])) == 1 and spec.get("allow_single_series_label") is True and
                        isinstance(entries[0], dict) and entries[0].get("label")):
                    series["series_label"] = str(entries[0]["label"])
                    series["legend_binding"] = "explicitly_allowed_single_series_single_label"
            cal = panel.get("calibration") or {}
            metadata.append({"image": panel.get("image"), "panel_id": panel.get("panel_id"),
                             "panel_label": spec.get("panel_label"),
                             "figure_title": spec.get("figure_title"),
                             "caption": spec.get("caption") or spec.get("caption_text"),
                             "caption_locator": spec.get("caption_locator"),
                             "axis": {axis: {"scale": (cal.get(axis) or {}).get("scale"),
                                             "unit": (cal.get(axis) or {}).get("unit"),
                                             "tick_pairs": (cal.get(axis) or {}).get("tick_pairs", []),
                                             "source": (cal.get(axis) or {}).get("source"),
                                             "rms_px": (cal.get(axis) or {}).get("rms_px")}
                                      for axis in ("x", "y")},
                             "legend_status": "declared" if entries else "not_reported_or_not_supplied",
                             "other_axes": spec.get("other_axes") or [],
                             "scale_bars": spec.get("scale_bars") or [],
                             "significance_note": spec.get("significance_note")})
    result["figure_metadata"] = metadata
    return result


def _norm_unit(value):
    return str(value or "").strip().replace("μ", "µ").replace(" ", "")


def align_claims(case, result):
    """Check explicit numeric claims against linked readings and their intervals."""
    claims = case.get("text_claims") or case.get("caption_claims") or []
    if not isinstance(claims, list):
        return [{"claim_id": None, "status": "unresolved",
                 "reason": "text_claims is not a list"}]
    # Index after legend binding / intervals.
    idx = {}
    for panel in result.get("panels", []):
        for series in panel.get("series", []):
            key = (panel.get("image"), panel.get("panel_id"), series.get("series_index"))
            idx[key] = (panel, series)
    aligned = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            aligned.append({"claim_id": "claim-%03d" % (i + 1), "status": "unresolved",
                            "reason": "claim is not an object"})
            continue
        cid = str(claim.get("claim_id") or "claim-%03d" % (i + 1))
        out = {"claim_id": cid, "statement": claim.get("statement"),
               "source_locator": claim.get("source_locator"), "status": "unresolved"}
        try:
            value = float(claim.get("value"))
            if not math.isfinite(value):
                raise ValueError("non-finite")
        except (TypeError, ValueError):
            out["reason"] = "numeric claim value is missing or unreadable"
            aligned.append(out)
            continue
        key = (claim.get("image"), claim.get("panel_id", "p1"), claim.get("series_index", 0))
        found = idx.get(key)
        if found is None:
            # A relative path is convenient in case.json; resolved paths live in the result.
            matches = [(k, v) for k, v in idx.items() if k[1:] == key[1:] and
                       str(k[0]).replace("\\", "/").endswith(str(claim.get("image") or "").replace("\\", "/"))]
            found = matches[0][1] if len(matches) == 1 else None
        if found is None:
            out["reason"] = "linked panel/series is unavailable or ambiguous"
            aligned.append(out)
            continue
        panel, series = found
        intervals = series.get("reading_intervals") or []
        point_index = claim.get("point_index", claim.get("bar_index", 0))
        if not isinstance(point_index, int) or not (0 <= point_index < len(intervals)):
            out["reason"] = "linked point/bar is unavailable"
            aligned.append(out)
            continue
        field = claim.get("field", "top" if series.get("chart_type") == "bar" else "y")
        measured = intervals[point_index].get(field)
        if not isinstance(measured, dict) or measured.get("estimate") is None:
            out["reason"] = "the requested value is uncalibrated; no numeric comparison is allowed"
            aligned.append(out)
            continue
        out.update({"linked_image": panel.get("image"), "panel_id": panel.get("panel_id"),
                    "series_index": series.get("series_index"), "series_label": series.get("series_label"),
                    "point_index": point_index, "field": field, "reading": measured,
                    "claimed_value": value, "claimed_unit": claim.get("unit")})
        if claim.get("unit") is not None and _norm_unit(claim.get("unit")) != _norm_unit(measured.get("unit")):
            out["status"] = "inconsistent"
            out["reason"] = "unit mismatch; values were not silently converted"
            aligned.append(out)
            continue
        tolerance = claim.get("tolerance", 0)
        try:
            tolerance = max(0.0, float(tolerance or 0))
        except (TypeError, ValueError):
            tolerance = 0.0
        out["comparison_rule"] = "claimed value must lie inside the raster interval expanded by the caller-declared tolerance"
        out["status"] = "consistent" if measured["lower"] - tolerance <= value <= measured["upper"] + tolerance else "inconsistent"
        if out["status"] == "inconsistent":
            out["reason"] = "numeric claim falls outside the linked reading interval; inspect both source and chart"
        aligned.append(out)
    return aligned


def write_readings_csv(readings, path):
    fields = ["image", "panel_id", "series_index", "series_label", "point_index", "bar_index",
              "x_estimate", "x_lower", "x_upper", "x_unit", "y_estimate", "y_lower", "y_upper",
              "y_unit", "reading_tier", "value_status"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in readings:
            flat = dict(row)
            for axis in ("x", "y"):
                interval_value = row.get(axis) or {}
                flat[axis + "_estimate"] = interval_value.get("estimate")
                flat[axis + "_lower"] = interval_value.get("lower")
                flat[axis + "_upper"] = interval_value.get("upper")
            writer.writerow(flat)
