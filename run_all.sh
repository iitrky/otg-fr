#!/bin/sh
# Reproduce every number, figure and document (about 20 minutes on 2 CPU cores).
set -e
cd "$(dirname "$0")"
python3 -m pytest -q tests                                                   # 12 unit tests
python3 experiments/exp1_channel_validation.py  > results/log_exp1.txt      # Tables 5-6, Fig. 3a-b
python3 experiments/exp2_time_domain.py         > results/log_exp2.txt      # Table 7, Fig. 3c
python3 experiments/exp3_restoration.py         > results/log_exp3.txt      # Tables 10 and 12, Figs 6-8
python3 experiments/exp4_scaling_robustness.py  > results/log_exp4.txt      # Fig. 8c, privacy accounting
python3 experiments/exp5_theory.py              > results/log_exp5.txt      # Propositions 2-3: Table 8, Fig. 4
python3 experiments/exp6_powertalk.py           > results/log_exp6.txt      # comparison with power talk: Table 9, Fig. 5
python3 experiments/exp7_sensitivity.py         > results/log_exp7.txt      # sensitivity and PV-ramp stress: Table 13, Fig. 9
python3 experiments/exp8_statistics.py          > results/log_exp8.txt      # effect sizes, Holm correction: Table 11
python3 experiments/make_figures.py                                          # Fig1-Fig9 (PNG, PDF, 600 dpi TIFF)
if command -v pandoc >/dev/null; then (cd manuscript && python3 build.py); fi   # Word documents
sh make_esm.sh                                                               # anonymized Online Resource 1
echo "Done: results/, results/figures/, manuscript/"
