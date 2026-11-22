"""Write the worked example's template package (.potx) — standard library only.

The example template is a genuine .potx-shaped OPC zip, so it cannot ship as a
text file. Instead the package ships the *builder*: this script regenerates the
template anywhere, deterministically, with the theme faces of your choice.

    python scripts/make_template.py --out examples/template.potx
    python scripts/make_template.py --out /app/work/template.potx --latin "Times New Roman" --ea "SimSun"

The layouts it provides ("Title Slide", "Title and Content") carry the same
title-placeholder geometry the generator writes, which is what makes the clean
worked example clean; point a spec's template.file at the file to run the
measured-template rules against it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_template as BT  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="make_template", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="path of the .potx to write")
    ap.add_argument("--latin", default="Arial", help="major/minor latin typeface")
    ap.add_argument("--ea", default="Microsoft YaHei", help="major/minor east-asian typeface")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    p = BT.build_template(out, latin=a.latin, ea=a.ea)
    print(json.dumps({"ok": True, "wrote": str(p), "bytes": p.stat().st_size},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
