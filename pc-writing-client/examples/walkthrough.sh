#!/usr/bin/env bash
# Minimal call example. Outputs are illustrative, not an official case result.
set -e
S=./ws.json
rm -rf "$S" ./out result.json workorder.json
python scripts/wcli.py --store $S load --text examples/example-draft.txt --case-id CASE-EXAMPLE \
  --references '[{"key":"doe2020"}]' --materials '[{"id":"M1"}]'
cat > workorder.json <<'EOF'
[{"id": "W1", "task": "replace the vague term"},
 {"id": "W2", "task": "reword the method sentence"}]
EOF
python scripts/wcli.py --store $S plan --workorder workorder.json
python scripts/wcli.py --store $S propose --edits examples/example-edits.json
python scripts/wcli.py --store $S accept --id E1
python scripts/wcli.py --store $S reject --id E2 --reason "keeps the agent voice"
python scripts/wcli.py --store $S apply
python scripts/wcli.py --store $S diff --from v0 --to v1
python scripts/wcli.py --store $S coverage
python scripts/wcli.py --store $S export --out ./out
python scripts/wcli.py --store $S result --out result.json
