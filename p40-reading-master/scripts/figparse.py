"""figparse — turn a scientific figure into structured, evidence-backed data.

Two entry points:

  python scripts/figparse.py calibrate --image FIG.png --out calib.json
      Detect panels, frames and tick pixel positions. Prints the tick
      positions the caller must label (by OCR) to finish calibration.

  python scripts/figparse.py run --case /input/case.json --out /app/output
      Full pass. Reads the tick labels recorded in the case file, calibrates,
      digitises every series, and writes result.json.

The tool never invents a tick value. If labels are missing it degrades to
`status: partial` and reports readings in axis fractions, which are honest but
not in physical units.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate as C  # noqa: E402
import contract as CT  # noqa: E402
import digitize as D  # noqa: E402
import pngio  # noqa: E402
import rasterkit as R_  # noqa: E402

SCHEMA_VERSION = "figparse/v1"


class ImageUnsupported(Exception):
    """The image format cannot be read in this environment, honestly."""


def _load_rgb(path: Path) -> list:
    """Rows of (r, g, b), read with the standard library.

    PNG (the format every plotting library exports and the bench generates) is
    decoded here directly, including 8/16-bit grey/RGB/palette/alpha. For other
    raster formats Pillow is used when it happens to be installed; when it is
    not, ImageUnsupported is raised and the caller reports an honest limit —
    the old hard `from PIL import Image` instead killed the whole route on
    machines without it.
    """
    try:
        return pngio.read_png_rgb(path)
    except pngio.PngError as exc:
        if str(path).lower().endswith((".png",)):
            raise ImageUnsupported(f"{path.name}: {exc}") from exc
    try:
        from PIL import Image  # optional acceleration for JPEG/TIFF/...
        with Image.open(path) as im:
            return [list(map(tuple, row)) for row in
                    (list(im.convert("RGB").getdata())[i * im.size[0]:
                                                       (i + 1) * im.size[0]]
                     for i in range(im.size[1]))]
    except Exception as exc:
        raise ImageUnsupported(
            f"{path.name}: not a decodable PNG and Pillow is unavailable "
            f"({type(exc).__name__}: {str(exc)[:120]})") from exc


def cmd_calibrate(args: argparse.Namespace) -> int:
    try:
        rgb = _load_rgb(Path(args.image))
    except (ImageUnsupported, OSError) as exc:
        report = {"schema_version": SCHEMA_VERSION, "image": str(args.image),
                  "panels": [], "limits": [f"image could not be read: {exc}"]}
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(json.dumps({"ok": False, "wrote": args.out, "reason": str(exc)[:160]}))
        else:
            print(text)
        return 5
    mask = C.dark_ink_mask(rgb)   # axis furniture only: bars must not read as spines
    panels = C.find_panels(mask)

    report = {"schema_version": SCHEMA_VERSION, "image": str(args.image), "panels": []}
    for p in panels:
        x0, y0, x1, y1 = p["bbox_px"]["x0"], p["bbox_px"]["y0"], p["bbox_px"]["x1"], p["bbox_px"]["y1"]
        sub = mask[y0:y1, x0:x1]
        frame = C.find_frame(sub)
        entry = {"panel_id": p["panel_id"], "bbox_px": p["bbox_px"], "frame_px": frame}
        if frame:
            entry["x_tick_px"] = [x0 + t for t in C.find_ticks(sub, frame, "x")]
            entry["y_tick_px"] = [y0 + t for t in C.find_ticks(sub, frame, "y")]
            entry["next_step"] = (
                "OCR the tick labels at these pixel positions, then pass the values "
                "as x_tick_values / y_tick_values to `figparse run`."
            )
        report["panels"].append(entry)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(json.dumps({"ok": True, "wrote": args.out, "panels": len(report["panels"])}))
    else:
        print(text)
    return 0


def _axis_reading(panel_mask, frame, spec: dict, axis: str) -> dict:
    """Calibrate one axis, trying sources in order of how much they can prove.

    The ladder exists because requiring every tick label is brittle: a single
    unreadable or spurious tick used to fail the whole axis and push the panel
    to `axis_fraction`. Each step down the ladder is weaker but still
    verifiable, and every result names the `source` it came from so a reviewer
    knows how much to trust it.

    1. tick positions + supplied values   -- residual proves the axis model
    2. same, with nulls for unread ticks  -- residual still proves it
    3. frame edges + declared axis limits -- no residual, stated as a caveat
    4. nothing                            -- axis_fraction, status partial
    """
    # Tick pixels and tick values are paired in reading order (left->right for
    # x, top->bottom for y). Fitting in that same raw pixel frame keeps the
    # pairing unambiguous: a y axis then simply gets a negative slope, because
    # image rows grow downward while the data axis grows upward. Digitisation
    # applies the fit to raw pixel coordinates too, so the two cannot disagree.
    px = C.find_ticks(panel_mask, frame, axis)
    raw = spec.get(f"{axis}_tick_values") or []
    scale = spec.get("x_scale" if axis == "x" else "y_scale", "auto")
    unit = spec.get(f"{axis}_unit")

    def _finish(fit: dict) -> dict:
        fit["unit"] = unit
        if axis == "y" and fit.get("ok"):
            # Convention: y_tick_values are listed in reading order (top ->
            # bottom), so a normal y axis fits with a negative slope. A positive
            # slope means either a genuinely inverted axis or values listed
            # bottom-up — either way a reviewer must see it, so it is recorded
            # rather than silently accepted.
            fit["values_increase_downward"] = fit["slope"] > 0
        return fit

    # --- 1 & 2: paired tick values, tolerating nulls for unread labels -------
    skipped: list[str] = []
    if raw and len(px) == len(raw):
        parsed = []
        for p, v in zip(px, raw):
            if v is None:
                continue
            try:
                parsed.append((p, float(v)))
            except (TypeError, ValueError):
                # A tick label that parses to no number is unread input: skip it and
                # say so, rather than crashing the digitisation.
                skipped.append(str(v)[:40])
        pairs = parsed
        if len(pairs) >= 2:
            fit = C.fit_axis([p for p, _ in pairs], [v for _, v in pairs], scale=scale)
            # A y axis normally has values decreasing down the page. If the fit
            # comes out the other way round, the overwhelmingly likely cause is
            # that the values were listed bottom-up rather than that the plot
            # has a genuinely inverted axis. Correct it, and say that we did —
            # reporting success while knowingly mirrored is the worst option.
            if (axis == "y" and fit.get("ok") and fit["slope"] > 0
                    and not spec.get("y_axis_inverted")):
                flipped = [(p, v) for p, v in reversed(pairs)]
                alt = C.fit_axis([p for p, _ in flipped], [v for _, v in flipped], scale=scale)
                if alt.get("ok"):
                    alt["orientation_corrected"] = True
                    alt["orientation_note"] = (
                        "supplied y_tick_values fitted with values increasing downward; "
                        "treated as a bottom-to-top list and reversed. Set "
                        "y_axis_inverted: true if this axis really is inverted."
                    )
                    fit = alt
            if fit.get("ok"):
                fit["label_source"] = "case_file"
                fit["source"] = "tick_labels"
                fit["ticks_paired"] = len(pairs)
                fit["ticks_detected"] = len(px)
                if skipped:
                    fit["skipped_labels"] = skipped
                fit["ticks_unread"] = len(px) - len(pairs)
                return _finish(fit)
        # Note: one label is deliberately not enough. A slope needs either two
        # labelled ticks or a declared limit; one label plus the pixel pitch
        # leaves the step size unknown, and assuming step=1 would silently
        # rescale the whole axis.

    # --- 3: frame edges plus declared limits --------------------------------
    limits = spec.get(f"{axis}_axis_limits")
    if isinstance(limits, (list, tuple)) and len(limits) == 2 and all(v is not None for v in limits):
        if axis == "x":
            fit = C.fit_from_limits(frame["left"], frame["right"], limits, scale=scale)
        else:
            # Frame top is the larger value on a normal y axis.
            fit = C.fit_from_limits(frame["top"], frame["bottom"], (limits[1], limits[0]), scale=scale)
        if fit.get("ok"):
            fit["unit"] = unit
            fit["label_source"] = "case_file"
            return _finish(fit)

    return {
        "ok": False,
        "reason": (
            f"no usable calibration for the {axis} axis: {len(px)} tick marks detected, "
            f"{len(raw)} tick values supplied. Supply one value per detected tick (null "
            f"where a label is unreadable), or give {axis}_axis_limits."
        ),
        "tick_px": px,
        "tick_values_supplied": len(raw),
        "unit": unit,
        "label_source": "missing",
        "source": "none",
    }


def _bar_series(i: int, col: dict, bars_info: dict, frame: dict, fx: dict, fy: dict,
                ink, x0: int, y0: int) -> dict:
    """One hue detected as solid bars: per-bar values, plus the marks above them.

    Each bar reports its top, the shared baseline and — when both axes are
    calibrated — the height top-minus-baseline, so a zero-based chart and an
    offset one can both be read without the tool assuming which is meant.
    Everything carries a `reading_tier`: `calibrated_digitised` when both axes
    fitted, `axis_fraction` when they did not.
    """
    cal_ok = bool(fx.get("ok") and fy.get("ok"))
    bl_px = bars_info["baseline_px"]
    rows = []
    for b in bars_info["bars"]:
        cx = (b["x0_px"] + b["x1_px"]) / 2.0
        if cal_ok:
            xv = float(C.px_to_value(cx, fx))
            top_v = float(C.px_to_value(b["top_px"], fy))
            base_v = float(C.px_to_value(b["bottom_px"], fy))
        else:
            xv = (cx - frame["left"]) / max(frame["right"] - frame["left"], 1)
            top_v = (frame["bottom"] - b["top_px"]) / max(frame["bottom"] - frame["top"], 1)
            base_v = (frame["bottom"] - b["bottom_px"]) / max(frame["bottom"] - frame["top"], 1)
        rows.append({
            "x_center": round(xv, 6),
            "top_value": round(top_v, 6),
            "baseline_value": round(base_v, 6),
            "height_value": round(top_v - base_v, 6) if cal_ok else None,
            "top_px": b["top_px"], "width_px": b["width_px"],
        })

    ann = D.find_annotations_above(ink, frame, bars_info["bars"])
    err_rows = []
    if cal_ok:
        for e in ann["error_bar_candidates"]:
            err_rows.append({
                "x": round(float(C.px_to_value(e["x_px"], fx)), 6),
                "center_y": round(float(C.px_to_value(e["y_px"], fy)), 6),
                "height_value": round(abs(e["height_px"] * fy["slope"]), 6),
                "kind": e["kind"],
            })

    # A bar chart drawn from zero should put the shared baseline at 0; if the
    # calibration disagrees, say so instead of quietly rebasing.
    baseline_note = None
    if cal_ok:
        base_v = rows[0]["baseline_value"] if rows else None
        if base_v is not None and abs(base_v) > 2 * float(abs(fy["slope"])):
            baseline_note = (
                f"the shared baseline reads as {base_v}, not 0: the chart may be drawn with "
                "an offset, a broken axis, or the calibration is off — check against the figure"
            )

    return {
        "series_index": i,
        "chart_type": "bar",
        "reading_tier": "calibrated_digitised" if cal_ok else "axis_fraction",
        "appearance": {"hue_bin": col["hue_bin"],
                       "median_hue_deg": round(col["median_hue"], 1),
                       "pixels": col["pixels"]},
        "n_bars": len(rows),
        "baseline_value": round(float(C.px_to_value(bl_px, fy)), 6) if cal_ok else None,
        "baseline_note": baseline_note,
        "bars": rows,
        "annotations": {
            "error_bar_candidates": err_rows,
            "marker_candidates": ann["marker_candidates"],
            "note": ("ink marks just above the bar tops: tall thin strokes read as error-bar "
                     "candidates, compact blobs as significance markers. Candidates only — a "
                     "reviewer confirms them against the figure"),
        } if (ann["error_bar_candidates"] or ann["marker_candidates"]) else {
            "error_bar_candidates": [], "marker_candidates": [],
            "note": "no marks detected above the bar tops"},
        "evidence": {
            "read_by": "solid-column detector: flat tops on a shared baseline inside the frame",
            "baseline_px": bl_px,
            "frame_px": {k: frame[k] for k in ("left", "top", "right", "bottom")},
            "panel_origin_px": [x0, y0],
        },
    }


def _digitise_panel(rgb, panel, spec) -> dict:
    x0, y0 = panel["bbox_px"]["x0"], panel["bbox_px"]["y0"]
    x1, y1 = panel["bbox_px"]["x1"], panel["bbox_px"]["y1"]
    sub_rgb = [row[x0:x1] for row in rgb[y0:y1]]
    # Axis furniture (frame, ticks) is near-black; data ink is saturated. Frame
    # and tick search run on the dark subset so solid bars never read as spines.
    axis_mask = C.dark_ink_mask(sub_rgb)
    full_mask = C.ink_mask(C.load_gray(sub_rgb))

    frame = C.find_frame(axis_mask)
    out = {"panel_id": panel["panel_id"], "bbox_px": panel["bbox_px"], "frame_px": frame,
           "series": [], "status": "undetermined", "notes": []}
    if frame is None:
        out["notes"].append(
            "No axis frame found in this panel. It is likely an image/gel/micrograph panel "
            "or the axes are unlabelled; digitisation by pixel-to-data calibration does not apply."
        )
        return out

    fx = _axis_reading(axis_mask, frame, spec, "x")
    fy = _axis_reading(axis_mask, frame, spec, "y")
    out["calibration"] = {"x": fx, "y": fy}

    if not (fx.get("ok") and fy.get("ok")):
        out["status"] = "partial"
        out["notes"].append(
            "Calibration incomplete, so readings are reported as axis fractions "
            "(0 = frame left/bottom, 1 = frame right/top) instead of physical values."
        )

    hsv = D.to_hsv(sub_rgb)
    colors = D.find_series_colors(sub_rgb, frame, hsv=hsv)
    if fy.get("values_increase_downward"):
        out["notes"].append(
            "y calibration has values increasing downward. If this figure's y axis is "
            "ordinary, the y_tick_values were listed bottom-to-top instead of top-to-bottom; "
            "re-run with the values reversed to confirm."
        )
    for i, col in enumerate(colors):
        m = D.series_mask(sub_rgb, frame, col["hue_bin"], hsv=hsv)

        # --- statistical charts: solid bars -------------------------------
        # A bar read through the curve path would come out as a horizontal line
        # through its middle, which is not a reading, it is an artefact. When
        # this colour forms flat-topped columns on a shared baseline, report
        # the bars themselves and skip the per-column trace.
        bars_info = D.detect_bars(m, frame)
        if bars_info:
            out["series"].append(_bar_series(
                i, col, bars_info, frame, fx, fy, full_mask, x0, y0))
            continue

        pts = D.extract_points(m, frame, n_markers=spec.get("n_markers", 0))
        if len(pts) < 3:
            continue
        pts = D.thin_curve(pts, spec.get("every", 1))

        xs_px = [p["x_px"] for p in pts]
        ys_px = [p["y_px"] for p in pts]

        if fx.get("ok") and fy.get("ok"):
            xs = C.px_to_value(xs_px, fx)
            ys = C.px_to_value(ys_px, fy)
            unit_x, unit_y = fx.get("unit"), fy.get("unit")
        else:
            xs = [(v - frame["left"]) / max(frame["right"] - frame["left"], 1) for v in xs_px]
            ys = [(frame["bottom"] - v) / max(frame["bottom"] - frame["top"], 1) for v in ys_px]
            unit_x = unit_y = "axis_fraction"

        thick = [float(p.get("thickness_px", 1)) for p in pts]
        # A stroked line is several pixels wide; its centre is only known to
        # about half the stroke, so convert that stroke width into data units
        # and report it as the per-point reading uncertainty.
        # On a log axis the same pixel error is multiplicative: half a stroke
        # becomes a constant *factor*, not a constant offset. Reporting a linear
        # bar there would understate the error at the top of the axis and
        # overstate it at the bottom.
        half_thick = float(R_.median(thick) / 2.0)
        if fy.get("ok") and fy.get("scale") == "log":
            factor = float(10 ** (half_thick * abs(fy["slope"])))
            y_unc = None
            y_unc_rel = round(factor - 1.0, 6)
            unc_basis = ("log axis: half the median stroke thickness converted to a "
                         "multiplicative factor; y_uncertainty_relative is the fractional "
                         "error, applied as y * (1 +/- that)")
        elif fy.get("ok"):
            y_unc = float(half_thick * abs(fy["slope"]))
            y_unc_rel = None
            unc_basis = ("half the median stroke thickness in pixels, converted through the "
                         "fitted y axis; it measures reading precision, not accuracy against "
                         "the underlying data")
        else:
            y_unc = float(half_thick / max(frame["bottom"] - frame["top"], 1))
            y_unc_rel = None
            unc_basis = "axis fraction, from half the median stroke thickness"

        # Error bars are reported as candidates, never asserted as measured
        # data: a steep line can mimic them, so the caller is told what they are.
        bars = D.find_error_bars(m, frame)
        if bars and fy.get("ok"):
            bars = [{"x_px": b["x_px"], "y_px": round(b["y_px"], 2),
                     "x": round(float(C.px_to_value(b["x_px"], fx)), 6) if fx.get("ok") else None,
                     "y": round(float(C.px_to_value(b["y_px"], fy)), 6),
                     "y_err": round(abs(b["half_length_px"] * fy["slope"]), 6),
                     "half_length_px": round(b["half_length_px"], 2)} for b in bars]
        else:
            bars = []

        out["series"].append({
            "series_index": i,
            "chart_type": "curve",
            "reading_tier": "calibrated_digitised" if (fx.get("ok") and fy.get("ok")) else "axis_fraction",
            "appearance": {"hue_bin": col["hue_bin"], "median_hue_deg": round(col["median_hue"], 1),
                           "pixels": col["pixels"]},
            "n_points": int(len(xs)),
            "x": [round(float(v), 6) for v in xs],
            "y": [round(float(v), 6) for v in ys],
            "x_unit": unit_x,
            "y_unit": unit_y,
            "y_uncertainty": None if y_unc is None else round(y_unc, 6),
            "y_uncertainty_relative": y_unc_rel,
            "uncertainty_basis": unc_basis,
            "error_bar_candidates": bars,
            "error_bar_note": (
                "tall isolated vertical strokes, reported as candidates: an error bar and a "
                "steep line segment look alike, so a reviewer must confirm against the figure"
            ) if bars else "none detected",
            "features": _features(xs, ys, y_unc if y_unc is not None else float(
                R_.median([abs(v) for v in ys]) * (y_unc_rel or 0.0))),
            "evidence": {
                "read_by": ("colour-mask column sampling inside the detected frame; dense "
                            "curves use [1,2,1]/4 sub-pixel smoothing with raw y retained"),
                "frame_px": {k: frame[k] for k in ("left", "top", "right", "bottom")},
                "panel_origin_px": [x0, y0],
            },
        })

    out["status"] = "success" if (out["series"] and fx.get("ok") and fy.get("ok")) else "partial"
    if not out["series"]:
        out["notes"].append("No saturated data series found inside the frame.")
    return out


def _features(xs, ys, y_unc: float) -> dict:
    """Summary descriptors that are true by construction from the digitised trace.

    Kept deliberately small: only quantities that a reader could verify by eye
    on the figure. Anything requiring a model assumption (fit parameters,
    derivative sign at a point) is left to the caller.
    """
    n = len(xs)
    if n < 2:
        return {}
    i_max = max(range(n), key=lambda i: ys[i])
    i_min = min(range(n), key=lambda i: ys[i])
    # Count direction changes on a lightly smoothed trace. On raw pixel data
    # the stroke jitter flips the sign of the difference almost every column,
    # so the raw count measures noise, not shape.
    w = max(3, (n // 60) * 2 + 1)
    w = min(w, n if n % 2 else n - 1)
    smooth = R_.moving_mean(list(ys), w) if w >= 3 else list(ys)
    flips = 0
    prev_sign = 0
    for i in range(1, len(smooth)):
        d = smooth[i] - smooth[i - 1]
        sign = (d > 0) - (d < 0)
        if sign != 0 and prev_sign != 0 and sign != prev_sign:
            flips += 1
        if sign != 0:
            prev_sign = sign
    # Net change across the whole trace, not the mean step: a monotone ramp has
    # a tiny mean step and a large net change, and "flat" would be wrong.
    net = float(ys[-1] - ys[0])
    return {
        "x_range": [round(float(min(xs)), 6), round(float(max(xs)), 6)],
        "y_max": round(float(ys[i_max]), 6),
        "y_max_at_x": round(float(xs[i_max]), 6),
        "y_min": round(float(ys[i_min]), 6),
        "y_min_at_x": round(float(xs[i_min]), 6),
        "y_span": round(float(max(ys) - min(ys)), 6),
        "direction_changes": flips,
        "direction_changes_basis": f"sign changes of the trace smoothed over {w} points",
        "trend": ("increasing" if net > 2 * y_unc else
                  "decreasing" if net < -2 * y_unc else "flat"),
        "trend_net_change": round(net, 6),
        "trend_basis": "net change from first to last point, compared against 2 x y_uncertainty",
    }


def cmd_run(args: argparse.Namespace) -> int:
    case_path = Path(args.case)
    try:
        case = CT.read_case(case_path)
    except ValueError as exc:
        result = _run_refused(case_path, str(exc))
        _write_result(args, result)
        return 5
    return _run_case(args, case_path, case)


def _run_refused(case_path: Path, message: str) -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "case_id": "UNKNOWN", "status": "undetermined", "panels": [],
            "limits": [f"the case could not be run as declared: {message}"[:200]],
            "provenance": {"tool": "figparse", "case_file": str(case_path),
                           "images_seen": 0}}


def _write_result(args: argparse.Namespace, result: dict) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({"ok": result.get("status") != "undetermined", "status": result.get("status"),
                      "panels": len(result.get("panels") or []),
                      "wrote": str(out_dir / "result.json")}, ensure_ascii=False))


def _run_case(args: argparse.Namespace, case_path: Path, case: dict) -> int:

    case_id = case.get("case_id") or case.get("id") or "UNKNOWN"
    if case_id == "UNKNOWN" and isinstance(case.get("case"), dict):
        case_id = case["case"].get("case_id") or "UNKNOWN"
    images = case.get("images") or case.get("figures") or []
    if isinstance(images, str):
        images = [images]
    malformed_images = not isinstance(images, list)
    if malformed_images:
        images = []

    result = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "status": "undetermined",
        "panels": [],
        "limits": (["images/figures must be a path or a list of image records"]
                   if malformed_images else []),
        "provenance": {"tool": "figparse", "case_file": str(case_path), "images_seen": len(images)},
    }

    for spec in images:
        if isinstance(spec, str):
            spec = {"path": spec}
        if not isinstance(spec, dict):
            result["limits"].append(
                f"an image entry was neither a path nor an object: {spec!r}"[:120])
            continue
        raw_path = spec.get("path") or ""
        if not isinstance(raw_path, (str, bytes)) or not raw_path:
            result["limits"].append(f"an image record has no usable path: {raw_path!r}"[:160])
            continue
        try:
            p = Path(raw_path)
            if not p.is_absolute():
                p = case_path.parent / p
            if not p.exists():
                result["limits"].append(f"image not found: {p}")
                continue
            rgb = _load_rgb(p)
            mask = C.ink_mask(C.load_gray(rgb))
            for panel in C.find_panels(mask):
                entry = _digitise_panel(rgb, panel, spec)
                entry["image"] = str(p)
                result["panels"].append(entry)
        except (ImageUnsupported, OSError, ValueError, TypeError) as exc:
            # A corrupt/unsupported image or malformed image record degrades only
            # that image; the case still receives a JSON result and other panels run.
            result["limits"].append(f"image could not be decoded: {exc}"[:200])
            continue
        except Exception as exc:
            result["limits"].append(
                f"image analysis was undetermined: {type(exc).__name__}: {str(exc)[:140]}"[:200])
            continue

    got = [p for p in result["panels"] if p.get("series")]
    if got and all(p["status"] == "success" for p in got):
        result["status"] = "success"
    elif got:
        result["status"] = "partial"
        result["limits"].append("Some panels are uncalibrated or contain no digitizable series.")
    else:
        result["status"] = "undetermined"
        result["limits"].append("No panel produced a digitizable calibrated series.")

    # Backfill the original case contract on graded success/partial runs. An
    # undetermined no-panel result stays a refusal and does not gain fake null answers.
    if result["status"] != "undetermined":
        CT.merge_result(result, case)
    _write_result(args, result)
    return CT.status_exit(result["status"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="figparse", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("calibrate", help="detect panels/frames/ticks; print tick pixel positions")
    c.add_argument("--image", required=True)
    c.add_argument("--out")
    c.set_defaults(func=cmd_calibrate)

    r = sub.add_parser("run", help="calibrate, digitise, and write result.json")
    r.add_argument("--case", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_run)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # final CLI boundary: no traceback escapes a reading case
        if args.cmd == "run":
            result = _run_refused(Path(args.case),
                                  f"the figure audit ended unexpectedly: {type(exc).__name__}: "
                                  f"{str(exc)[:160]}")
            try:
                _write_result(args, result)
            except Exception:
                print(json.dumps({"ok": False, "status": "undetermined", "wrote": None},
                                 ensure_ascii=False))
            return 5
        report = {"schema_version": SCHEMA_VERSION, "status": "undetermined",
                  "limits": [f"calibration failed: {type(exc).__name__}: {str(exc)[:160]}"]}
        if args.out:
            try:
                Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
            except OSError:
                pass
        print(json.dumps(report, ensure_ascii=False))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
