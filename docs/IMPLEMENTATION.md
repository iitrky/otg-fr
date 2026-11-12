# OTG-FR — Complete implementation guide

Authors: Arul Dalton G (corresponding, aruldalton@saveetha.ac.in) and Marisargunam S, Saveetha Engineering College, Chennai, India.

This document maps every equation and algorithm step in the manuscript to the code. It also lists every parameter and how each experiment is constructed, and shows how to extend the work. Line numbers refer to v1.0.0.

---

## 1. Concept in one paragraph

In an islanded network held up by grid-forming (GFM) inverters with P–f droop, the steady-state frequency deviation is

$$\Delta\omega=\frac{\sum_k P_k^{\rm set}+P_{\rm PV}-P_{\rm load}-P_{\rm loss}}{\sum_k D_k}.$$

It is a **sum** of all set-points divided by an (unknown) total stiffness. If every zone adds a small zero-mean pilot $p_k(t)=A\sum_m z_{k,m}c_m(t)$ built from orthogonal codes $c_m$, then correlating the frequency with code $m$ gives $y_m = A\sum_k z_{k,m}/\sum_k D_k$. The ratio of two such correlations yields a weighted average $\sum_k w_kx_k/\sum_k w_k$ in which the unknown network, losses, droop gains and amplitude all cancel. The power network therefore acts as the **aggregation server** of a federated algorithm, with no telecom.

---

## 2. Repository map

| Path | Content |
|---|---|
| `otgfr/network.py` | IEEE 33-bus island, zones, DER data, Newton droop AC power flow |
| `otgfr/rcd.py` | **Algorithm 2** (RCD): Walsh codes, encoder, ratio decoder, linear channel, DP accounting |
| `otgfr/restoration.py` | **Algorithm 1** (OTG-FR), cold-load pick-up learner, planner, physics, baselines |
| `experiments/exp1_channel_validation.py` | AC chip-by-chip validation (Fig. 2a–b) |
| `experiments/exp2_time_domain.py` | Small-signal inverter dynamics, chip-duration sweep (Fig. 2c) |
| `experiments/exp3_restoration.py` | 100-scenario closed-loop Monte Carlo + Wilcoxon tests (Figs 3–5) |
| `experiments/exp4_scaling_robustness.py` | N-scaling, inverter trip, privacy ε (Fig. 5c) |
| `experiments/make_figures.py` | Fig1–Fig6 (system diagram, architecture block diagram, results) in PNG, PDF and 600 dpi TIFF |
| `tests/` | 11 pytest unit/integration tests |
| `results/` | JSON outputs, logs, `figures/` (Fig1–Fig6) |
| `manuscript/` | Word documents (complete paper, anonymized manuscript, title page), Markdown sources, `references.py` (APA 7, Crossref-verified), `build.py`, `submission/` |
| `make_esm.sh` | Builds the anonymized supplementary archive `ESM_1.zip` (Online Resource 1) |

---

## 3. Physical model — `otgfr/network.py`

### 3.1 Network (`build_network`, line 39)
- Data: `pandapower.networks.case33bw()` (Baran & Wu 1989). Base 1 MVA, 12.66 kV, 60 Hz.
- Substation (bus 1, index 0) is lost; ties 18–33 and 25–29 (0-indexed `(17,32)`, `(24,28)`) are closed (`TIES_CLOSED`).
- The admittance matrix $Y$ is built directly from line R and X in ohms.

### 3.2 Zones and DER (`ZONES`)

| Zone | Buses (0-idx) | GFM bus | BESS MW / MWh | PV MW |
|---|---|---|---|---|
| Z1 urban core | 0–4, 18–24 | 2 | 0.6 / 2.0 | 0.3 |
| Z2 civic | 5–12 | 7 | 0.8 / 2.5 | 0.4 |
| Z3 solar park | 13–17 | 15 | 1.6 / 7.0 | 2.0 |
| Z4 utilities | 25–32 | 29 | 0.8 / 2.5 | 0.5 |

Droop: $D_k = P_k^{\rm rated}/m_p$ with $m_p=0.02$ (`MP`). SoC-adaptive droop scales this to $D_k\cdot\max(\text{SoE}_k,0.02)$ (`droop_gains`). Q–V droop: $Q_k=(V_0-V_k)/(n_q P_k^{\rm rated})$ with $n_q=0.05$ and $V_0=1.03$.

### 3.3 Islanded droop power flow (`droop_powerflow`, line 67)
- Unknowns: $\theta_i$ for all buses except the first GFM bus, $|V_i|$ for all buses, and the common $\Delta\omega$: $2n$ unknowns.
- Equations: active and reactive mismatch at every bus: $2n$ equations.
- Injections: $P^{\rm spec}_i=\sum_{k\in i}(P^{\rm set}_k-D_k\Delta\omega)-P^L_i+P^{PV}_i$ and $Q^{\rm spec}_i=\sum_{k\in i}(V_0-|V_i|)/n_{q,k}-Q^L_i$.
- Jacobian: MATPOWER-style $\partial S/\partial\theta$ and $\partial S/\partial|V|$, plus the droop columns $\partial F_P/\partial\Delta\omega=D_k$ and $\partial F_Q/\partial|V_k|=1/n_{q,k}$.
- Converges in 3–5 Newton iterations (~3.5 ms). It supports warm start (`x0`). The tests verify power balance, proportional sharing and $\Delta\omega$ = imbalance/stiffness.

---

## 4. Algorithm 2 — Ratio-Coded Droop aggregation — `otgfr/rcd.py`

| Step | Code |
|---|---|
| Codes: highest-sequency non-DC Hadamard rows (reject drift) | `walsh_codes` (l. 27) |
| Code allocation: 1 "ones" code; each quantity gets a numerator code; weighted quantities also get a denominator code | `RCDChannel.__init__` (l. 45) |
| Normalisation $z_{num}=\tilde w\tilde x$, $z_{den}=\tilde w$, $z_{ones}=\tfrac12$, unweighted $z=\tfrac12\tilde x$; optional dither $\mathcal N(0,\sigma^2)$ | `contributions` (l. 64) |
| Pilot $p_k(t)=A\,Z_k C$ | `pilot_powers` (l. 82) |
| Correlation $y=C\,\Delta\omega/L$ and ratio $\hat x=s\,y_{num}/y_{den}$ | `decode` (l. 86) |
| Fast channel $\Delta\omega=(\sum p - \Delta P_{load})/\sum D$ + PLL noise (validated against AC within 0.19 mHz) | `linear_channel` (l. 97) |
| zCDP accounting $\rho=n\Delta^2/2\sigma^2$, $\varepsilon=\rho+2\sqrt{\rho\ln(1/\delta)}$ | `zcdp_epsilon` (l. 109) |
| Amplitude control $A\leftarrow A\cdot 2^{\mathrm{round}(4\log_2(\Delta f^*/\Delta f_{pk}))/4}$, cap 15 kW | `restoration.run` (amplitude-control block after `linear_channel` call) |
| Chip shaping: raised cosine over 25% of chip; integrate second half | `experiments/exp2_time_domain.py` (`RAMP`) |

Why the ratio cancels everything: both correlations share the factor $A/\sum_k D_k$. All zones apply the same quantised amplitude gain because they observe the same frequency peak.

---

## 5. Algorithm 1 — OTG-FR — `otgfr/restoration.py`

### 5.1 Exogenous scenario (`make_scenario`, l. 79)
Each scenario draws:
- Load-block priority classes: critical buses 3, 6, 29; essential buses 23, 31; plus 30% random essential (10% in Z3).
- Social index $\omega_b = w_{class}(1+0.2u)$.
- CLPU truth: $m\sim U(1.5,2.8)$ and $\tau\sim U(0.5,2.5)$ h, with zone deviations of 5% and 10%.
- Day type: 0.9 / 0.6 / 0.3 with probabilities 0.4 / 0.4 / 0.2.
- Correlated cloud processes, PV forecast error of 15%, load noise of 3%, telemetry noise of 2%, and initial SoE $U(0.7,0.95)$.

The seed is `10000 + scenario` and is identical for every method, so all comparisons are paired.

### 5.2 Load and CLPU model
$p_b(t)=p_b\,g(t)\,[1+(m_{\rm eff,b}-1)e^{-a/\tau}]$, with $m_{\rm eff,b}=1+(m-1)(1-e^{-d_b/3\,h})$. Here $g$ is the hourly residential profile `G_HOURLY`, $a$ is the age since energisation and $d_b$ the outage duration (2 h before the window starts).

### 5.3 CLPU learner (`CLPULearner`, l. 110)
- A grid likelihood over $m\in[1.2,3.2]$ (41 points) and $\tau\in[0.25,3]$ (45 points), with Gaussian telemetry error of 2%. Updates are vectorised.
- `likelihood_summary` returns the likelihood-only mean $\mu_k$ and precision $\Lambda_k$, so the prior is never double-counted across zones.
- `personalised_estimate` (l. 143) computes $\theta_k=(\Lambda_0\mu_0+\Lambda_k\mu_k+\kappa\Lambda_{-k}\hat\mu_{pop})/(\Lambda_0+\Lambda_k+\kappa\Lambda_{-k})$ with $\kappa=0.5$. This partial personalisation carries the idea of the authors' earlier FedPPA work over to the new setting.

### 5.4 Zone planner (`zone_plan`, l. 154)
- For every block, over the remaining horizon: nominal value $V_b=\omega_b\sum_t p_bg_t\Delta t$ and energy $E_b$ including predicted CLPU.
- Keep an energised block if $V_b+\rho_b\ge\lambda E_b$, with $\rho_b=\omega_bp_b\cdot 8$ h (`RHO_H`). This test is applied **only when the zone perceives an island deficit** (no-regret rule).
- Pick up an off block if $V_b\ge\lambda E_b$.
- Surplus trajectory: $s\leftarrow\min(s+(PV^{fc}-L)\Delta t\,\eta^{\pm1},E_{cap})$, reported at 2, 6, 10, 14 and 24 h (`CHECKPOINTS_H`).
- Pick-up requests are ordered by $\omega_b$, and their power includes the CLPU peak.

### 5.5 Main loop (`run`, l. 191) — per 15-min step

1. **CLPU estimates** (`# ---- CLPU estimates`): local summaries, then personalised estimates.
2. **Price negotiation** (`# ---- price negotiation`), for `ROUNDS = 3` rounds:
   - plan at current $\lambda_k$, then build the quantity vector (5 surplus checkpoints, headroom, request, CLPU mean pair with weights $\Lambda/(\Lambda+\Lambda_0)$, precision pair);
   - **OTG:** encode, pilot, `linear_channel`, then each zone decodes its *own* frequency, followed by amplitude control;
   - **Telecom:** exact averages over zones whose Markov link is up (the coordinator extrapolates missing zones); zones that are down plan locally;
   - price update $\lambda_k\leftarrow\lambda_k\exp(\mathrm{clip}(-\eta g,\pm0.25))$ with $g=(N\min_h\bar S_h-0.05E_{cap})/E_{cap}$ and $\eta=1$; set the deficit flag if $g<0$;
   - federated CLPU fusion.
3. **Apply decisions** (`# ---- apply decisions`): planned sheds, then pick-ups within the shared power fraction $\varphi=\min(1,N\bar h/N\bar r)$.
4. **Physics** (`# ---- physics`):
   - true demand, then UFLS (trip the lowest $\omega$ while demand exceeds $\sum\min(P^{rated},\text{energy}/\Delta t)$);
   - droop sharing ∝ $D_k$ with power and energy caps and redistribution; charging ∝ $P^{rated}(1-\text{SoE})$; efficiency 0.95; minimum SoE 5%;
   - optional full AC droop power flow for voltage checks.
5. **Learning and logging** (`# ---- book-keeping and learning`).

### 5.6 Methods (argument `method`)

| Method | Information | Sharing physics |
|---|---|---|
| `full_info` | true CLPU, perfect PV, exact aggregates, 16-step bisection on λ | SoC droop |
| `local_rating` | own data only | rating droop |
| `local_soc` | own data only | SoC droop |
| `telecom` (+`p_link`) | same planner, aggregates via Markov telecom links (mean outage 2 h) | SoC droop |
| `otg` / `otg_dp` (+`dp_sigma`) | same planner, aggregates via RCD | SoC droop |

Options: `otg_len`, `otg_amp`, `load_sigma_frac`, `fuse_clpu`, `pf_check`.

### 5.7 Key parameters

| Name | Value | Meaning |
|---|---|---|
| `DT`, `STEPS`, `H0` | 0.25 h, 96, 18:00 | horizon |
| `ROUNDS` | 3 | RCD rounds per step (3 × 128 s) |
| `otg_len`, `otg_amp` | 128 chips, 6 kW | code length, initial pilot amplitude |
| `DF_TARGET_HZ`, `AMP_MAX_MW` | 0.10 Hz, 15 kW | amplitude control |
| `ETA_LAMBDA`, `MAX_LOG_STEP` | 1.0, 0.25 | price step, trust region |
| `RHO_H` | 8 h | re-interruption penalty |
| `KAPPA` | 0.5 | weight of other zones' CLPU information |
| `SOE_MIN`, `ETA` | 0.05, 0.95 | battery limits |

---

## 6. Experiments

| Exp | Design | Output |
|---|---|---|
| 1 | Per chip: Newton droop AC PF with per-bus load noise (0.5% of island load), drift, undisclosed SoC gains, 1 mHz PLL noise; 60 AC rounds × 4 amplitudes; 400 linear rounds per sweep point | `exp1_channel_validation.json` |
| 2 | Linearised GFM dynamics (filter 0.05 s, coupling reactance 0.15 p.u., Kron-reduced network), exact discretisation; chip duration 0.05–1 s | `exp2_time_domain.json` |
| 3 | 100 scenarios × 17 configurations, 4 processes; Wilcoxon paired tests | `exp3_restoration.json` (`summary`, `tests`, `per_scenario`; scenario 0 also has traces) |
| 4 | N = 4…64 zones; inverter trip removing 30% of stiffness mid-round; zCDP ε | `exp4_scaling_robustness.json` |

Runtime is about 4 minutes on 4 cores. All random streams are seeded, so a rerun reproduces every number exactly.

---

## 7. Main results (reproduced by `run_all.sh`)

| Method | Priority-weighted energy (% of full info) | Critical energy served | Re-interruptions/day |
|---|---|---|---|
| Local, rating droop | 73.6 [72.3, 74.9] | 80.1% | 43.7 |
| Local, SoC droop | 77.2 [75.9, 78.5] | 84.9% | 45.0 |
| Telecom FL, p = 0.9 | 87.9 [86.4, 89.3] | 89.7% | 57.2 |
| Telecom FL, p = 1.0 | 99.9 | 99.8% | 59.4 |
| **OTG-FR (no telecom)** | **96.7 [96.4, 97.0]** | **99.9%** | 39.1 |

---

## 8. Extending the work

- **Another feeder:** replace `build_network` (any pandapower net), edit `ZONES`, and keep `LOAD_BLOCKS` derived from loads.
- **More zones:** RCD needs one code per quantity, independent of N. Raise `length` if the quantity count exceeds `length − 1`.
- **Other federated tasks:** any statistic expressible as $\sum w_kx_k/\sum w_k$ (state estimation, forecasting, gradient averaging) can reuse `RCDChannel` directly.
- **Hardware-in-the-loop:** replace `linear_channel` with frequency samples from inverter controllers and keep `decode` unchanged.

## 9. Known limitations (also stated in the paper)
- The evidence is computational. The closed loop uses the AC-validated linear channel, a single feeder and synthetic priorities.
- Re-interruptions (39 per day) exceed those of the full-information coordinator (1.8), because only a few price iterations fit in each step.
- Formal differential privacy at usable dither levels is weak. The privacy property claimed is structural only.
- There is no defence yet against a malicious zone injecting biased pilots.
