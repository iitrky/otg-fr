#!/bin/sh
# Build ESM_1.zip: the anonymized code-and-data archive cited as "Online Resource 1" (double-blind review).
set -e
cd "$(dirname "$0")"
TMP=$(mktemp -d); mkdir -p "$TMP/code"
cp -r otgfr experiments tests results run_all.sh requirements.txt "$TMP/code/"
rm -f "$TMP"/code/results/figures/*.tif
find "$TMP/code" -name __pycache__ -prune -exec rm -rf {} +
cat > "$TMP/code/README.md" <<'TXT'
# Online Resource 1 - code and data
Supplementary material for "Grid Frequency as the Aggregation Channel for Federated Restoration of Islanded Microgrids"
(anonymized for double-blind review). Reproduce all results: `pip install -r requirements.txt && sh run_all.sh`
TXT
printf 'MIT License\n\nCopyright (c) 2026 The authors (names withheld for double-blind review)\n' > "$TMP/code/LICENSE"
if grep -rIqiE "dalton|marisargunam|saveetha|iitrky" "$TMP/code"; then echo "identifying text found"; exit 1; fi
mkdir -p manuscript/submission
(cd "$TMP/code" && python3 -c "import shutil; shutil.make_archive('../ESM_1','zip','.')")
mv "$TMP/ESM_1.zip" manuscript/submission/ESM_1.zip; rm -rf "$TMP"
echo "written manuscript/submission/ESM_1.zip"
