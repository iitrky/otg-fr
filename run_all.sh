#!/bin/sh
# Reproduce every number, figure and document (about 5 minutes on 4 CPU cores).
set -e
cd "$(dirname "$0")"
python3 -m pytest -q tests                                                   # 11 unit tests
python3 experiments/exp1_channel_validation.py  > results/log_exp1.txt      # Tables 5-6, Fig. 3a-b
python3 experiments/exp2_time_domain.py         > results/log_exp2.txt      # Table 7, Fig. 3c
python3 experiments/exp3_restoration.py         > results/log_exp3.txt      # Tables 8-9, Figs 4-6
python3 experiments/exp4_scaling_robustness.py  > results/log_exp4.txt      # Fig. 6c, privacy accounting
python3 experiments/make_figures.py                                          # Fig1-Fig6 (PNG, PDF, 600 dpi TIFF)
if command -v pandoc >/dev/null; then (cd manuscript && python3 build.py); fi   # Word documents
sh make_esm.sh                                                               # anonymized Online Resource 1
echo "Done: results/, results/figures/, manuscript/"
