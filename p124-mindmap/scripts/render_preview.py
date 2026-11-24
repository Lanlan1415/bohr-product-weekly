#!/usr/bin/env python3
"""Render a real PNG from mindmap.svg only when an actual renderer is available.

Exit 0 = PNG written and magic bytes verified. Exit 2 = usage. Exit 6 = no
renderer, failed rendering or missing/invalid output. There is no SVG-extension
renaming fallback and no claim that a preview exists when rendering was impossible.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", required=True)
    parser.add_argument("--png", required=True)
    args = parser.parse_args(argv)
    svg, png = Path(args.svg).resolve(), Path(args.png).resolve()
    if not svg.is_file():
        parser.error("SVG does not exist")
    png.parent.mkdir(parents=True, exist_ok=True)
    rsvg, inkscape = shutil.which("rsvg-convert"), shutil.which("inkscape")
    try:
        if rsvg:
            result = subprocess.run([rsvg, "--output", str(png), str(svg)], capture_output=True, text=True, timeout=120)
            renderer = "rsvg-convert"
        elif inkscape:
            result = subprocess.run([inkscape, str(svg), "--export-type=png", "--export-filename=" + str(png)],
                                    capture_output=True, text=True, timeout=120)
            renderer = "inkscape"
        else:
            try:
                import cairosvg
            except (ImportError, OSError):
                print('{"status":"undetermined","reason":"no CairoSVG, rsvg-convert or inkscape renderer available","exit":6}')
                return 6
            cairosvg.svg2png(url=str(svg), write_to=str(png))
            result, renderer = None, "cairosvg"
        if result is not None and result.returncode != 0:
            print('{"status":"undetermined","reason":"renderer failed","exit":6}')
            return 6
        data = png.read_bytes() if png.exists() else b""
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            print('{"status":"undetermined","reason":"no valid PNG was written","exit":6}')
            return 6
        print('{"status":"clean","renderer":"%s","bytes":%d}' % (renderer, len(data)))
        return 0
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        print('{"status":"undetermined","reason":"%s","exit":6}' % str(exc).replace('"', "'")[:180])
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
