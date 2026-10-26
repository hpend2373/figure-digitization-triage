#!/usr/bin/env bash
# Run every Python suite in the package and require exactly one scenario marker
# from each. Used by both CI jobs; a person can run it too:
#
#     bash .github/run_suites.sh
#
# By GLOB, not by a list somebody has to keep: a new suite is run the moment it
# exists, and `tests/test_reproducibility.py` checks that these globs are the
# ones the suites live under.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
: > scenario-counts.tsv
for t in tests/test_*.py tests/sheet/test_*.py; do
  echo "--- $t"
  # CAPTURED, NOT PIPED. `python "$t" | tee` reports tee's exit status, so a
  # failing suite would go green. Printed on the way out either way.
  if ! out="$("$PY" "$t" 2>&1)"; then
    printf '%s\n' "$out"
    echo "FAILED: $t"
    exit 1
  fi
  printf '%s\n' "$out"
  # EXACTLY ONE marker, and not zero: a suite printing its verdict twice, or a
  # suite that ran nothing, must not read as a pass.
  markers="$(printf '%s\n' "$out" | sed -nE 's/^FDT_SCENARIOS_RUN=([0-9]+)$/\1/p')"
  if [ "$(printf '%s\n' "$markers" | grep -c .)" -ne 1 ]; then
    echo "$t printed $(printf '%s\n' "$markers" | grep -c .) FDT_SCENARIOS_RUN lines; it must print exactly one"
    exit 1
  fi
  if [ "$markers" -eq 0 ]; then
    echo "$t ran 0 scenarios"
    exit 1
  fi
  printf '%s\t%s\n' "$t" "$markers" >> scenario-counts.tsv
done
echo
echo "scenarios per suite:"
cat scenario-counts.tsv
awk -F'\t' '{s += $2} END {print "TOTAL\t" s}' scenario-counts.tsv
