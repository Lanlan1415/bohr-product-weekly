#!/usr/bin/env bash
# Minimal call example. Outputs below are illustrative, not an official case result.
set -e
# Start from an empty workspace: a store left over from an earlier document keeps
# anchors that no longer resolve, which verify() will correctly report as invalid.
S=./ws.json
rm -f "$S" session.md
python scripts/cli.py --store $S open --doc-id paper --text examples/example-doc.txt --page-starts 0,2
python scripts/cli.py --store $S find --doc-id paper --quote "Uptake rose three-fold"
python scripts/cli.py --store $S ask --doc-id paper --quote "Uptake rose three-fold" \
  --question "what was the measured effect?" --answer "uptake rose three-fold under the coating"
python scripts/cli.py --store $S note --doc-id paper --quote "Only one coating thickness" \
  --text "the report itself flags this limitation"
python scripts/cli.py --store $S export --out session.md
python scripts/cli.py --store $S verify
