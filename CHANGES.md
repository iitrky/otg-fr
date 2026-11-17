# Changes in v2.0 (methodology and novelty revision, November 2026)

Method
- RCD: Walsh codes are now selected in decreasing polynomial drift order (popcount of the Hadamard row index) instead of
  highest sequency. Every code used then rejects net-load/PV drift up to degree 4 exactly (Proposition 2); the v1.0
  ordering rejected only constants on its first code. `walsh_codes(..., order="sequency")` reproduces v1.0.
- OTG-FR: ergodic (geometric-mean) averaging of each zone's price copies over the R rounds of a step, R = 5 (v1.0: R = 3,
  no averaging). Removes the odd/even-R oscillation of the dual update and cuts re-interruptions about fourfold.
- linear_channel: optional deterministic ramp (PV change during a round) for stress tests.

Analysis (manuscript Section 3.3): Propositions 1-4 (invariance, drift rejection, closed-form decoding error with
validity range, excursion bound), aggregation-gain corollary versus time-slotted signalling, complexity.

New experiments
- exp5_theory.py: verification of Propositions 2-3 (linear channel and chip-by-chip AC power flow).
- exp6_powertalk.py: factorial comparison with power talk (time-slotted vs coded, assumed gain vs ratio decoding).
- exp7_sensitivity.py: one-at-a-time sensitivity of R, price averaging, eta, rho, kappa; PV-ramp stress.
- exp8_statistics.py: bootstrap CIs, Hodges-Lehmann, rank-biserial effect sizes, Holm correction.
- exp3 adds ablations otg_v1, otg_no_price_avg, otg_sequency_codes. v1.0 results are reproduced exactly by otg_v1.

All experiments were rerun with the new defaults; manuscript tables are generated from results/*.json.
