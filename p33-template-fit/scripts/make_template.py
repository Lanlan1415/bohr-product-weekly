"""Create a real two-layout PPTX template for the worked example.

The fixture starts from the same renderer-tested PresentationML package as the
runtime generator, then adds native title/body placeholders and valid master
relationships. It writes a binary runtime artifact; nothing binary ships in the
skill package.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_delivery4 import native_template  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="make_template", description=__doc__)
    ap.add_argument("--out", required=True, help="output .pptx template path")
    ap.add_argument("--latin", default="Arial", help="major/minor latin typeface")
    ap.add_argument("--ea", default="Microsoft YaHei", help="major/minor east-asian typeface")
    args = ap.parse_args(argv)
    source = native_template("documented-example", latin=args.latin, ea=args.ea)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out)
    print(json.dumps({"ok": True, "wrote": str(out), "bytes": out.stat().st_size,
                      "layouts": ["Title Slide", "Title and Content"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
