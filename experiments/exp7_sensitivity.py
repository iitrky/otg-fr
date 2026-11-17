"""
Experiment 7 - Parameter sensitivity of OTG-FR and PV-ramp stress test (100 paired scenarios each).

(a) One-at-a-time sensitivity of Algorithm 1 to its design parameters around the defaults
    (rounds per step R = 5 with ergodic price averaging, price step eta = 1, re-interruption
    penalty rho = 8 h, CLPU fusion weight kappa = 0.5), including R without price averaging.
(b) PV-ramp stress: the PV change that occurs during each RCD round is injected into the channel
    as a deterministic net-load ramp (linear + quadratic), scaled by 5x and 10x (cloud-edge events,
    up to about 0.9 MW per round), for the proposed drift-ordered and the v1.0 sequency-ordered codes.
PWES is reported relative to the full-information coordinator of the same scenario.
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from multiprocessing import Pool
from scipy import stats
from otgfr.restoration import make_scenario, run

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
N_SCEN = 100
CONFIGS = {
    "default": {},
    "R=1": dict(overrides=dict(ROUNDS=1)), "R=2": dict(overrides=dict(ROUNDS=2)), "R=3": dict(overrides=dict(ROUNDS=3)),
    "R=4": dict(overrides=dict(ROUNDS=4)), "R=7": dict(overrides=dict(ROUNDS=7)),
    "no_avg_R=3": dict(overrides=dict(ROUNDS=3, PRICE_AVG=False)), "no_avg_R=4": dict(overrides=dict(ROUNDS=4, PRICE_AVG=False)),
    "no_avg_R=5": dict(overrides=dict(PRICE_AVG=False)),
    "eta=0.5": dict(overrides=dict(ETA_LAMBDA=0.5)), "eta=2": dict(overrides=dict(ETA_LAMBDA=2.0)),
    "rho=0h": dict(overrides=dict(RHO_H=0.0)), "rho=4h": dict(overrides=dict(RHO_H=4.0)),
    "rho=16h": dict(overrides=dict(RHO_H=16.0)), "rho=32h": dict(overrides=dict(RHO_H=32.0)),
    "kappa=0": dict(overrides=dict(KAPPA=0.0)), "kappa=1": dict(overrides=dict(KAPPA=1.0)),
    "ramp5_drift": dict(pv_ramp=5.0), "ramp5_sequency": dict(pv_ramp=5.0, code_order="sequency"),
    "ramp10_drift": dict(pv_ramp=10.0), "ramp10_sequency": dict(pv_ramp=10.0, code_order="sequency"),
}
KEYS = ["pwes", "crit_frac", "reint_total", "reint_ufls", "agg_err", "df_pilot_mhz", "vmin"]


def one(seed):
    scn = make_scenario(seed)
    out = {"_ref": run(scn, "full_info", pf_check=False)["pwes"]}
    for name, kw in CONFIGS.items():
        L = run(scn, "otg", pf_check=(name == "default" or name.startswith("ramp")), **kw)
        out[name] = {k: float(L[k]) for k in KEYS}
    return out


def ci(x):
    x = np.asarray(x, float); m = x.mean(); h = 1.96 * x.std(ddof=1) / np.sqrt(len(x))
    return [float(m), float(m - h), float(m + h)]


def main():
    t0 = time.time()
    with Pool(min(4, os.cpu_count() or 1)) as pool:
        per = pool.map(one, range(N_SCEN))
    ref = np.array([p["_ref"] for p in per])
    summary, tests = {}, {}
    base = np.array([p["default"]["pwes"] for p in per]) / ref * 100
    base_re = np.array([p["default"]["reint_total"] for p in per])
    for name in CONFIGS:
        rel = np.array([p[name]["pwes"] for p in per]) / ref * 100
        summary[name] = dict(pwes_rel_pct=ci(rel), **{k: ci([p[name][k] for p in per]) for k in KEYS})
        if name != "default":
            re = np.array([p[name]["reint_total"] for p in per])
            tests[name] = dict(pwes_diff=float((rel - base).mean()),
                               p_pwes=float(stats.wilcoxon(rel, base).pvalue) if np.any(rel != base) else 1.0,
                               reint_diff=float((re - base_re).mean()),
                               p_reint=float(stats.wilcoxon(re, base_re).pvalue) if np.any(re != base_re) else 1.0)
    for a, b in [("ramp5_drift", "ramp5_sequency"), ("ramp10_drift", "ramp10_sequency")]:
        x = np.array([p[a]["pwes"] for p in per]) / ref * 100; y = np.array([p[b]["pwes"] for p in per]) / ref * 100
        xa = np.array([p[a]["agg_err"] for p in per]); ya = np.array([p[b]["agg_err"] for p in per])
        xu = np.array([p[a]["reint_ufls"] for p in per]); yu = np.array([p[b]["reint_ufls"] for p in per])
        tests[f"{a}_vs_{b}"] = dict(pwes_diff=float((x - y).mean()), p_pwes=float(stats.wilcoxon(x, y).pvalue),
                                    agg_err_diff=float((xa - ya).mean()), p_agg=float(stats.wilcoxon(xa, ya).pvalue),
                                    ufls_diff=float((xu - yu).mean()),
                                    p_ufls=float(stats.wilcoxon(xu, yu).pvalue) if np.any(xu != yu) else 1.0)
    json.dump(dict(summary=summary, tests=tests), open(os.path.join(OUT, "exp7_sensitivity.json"), "w"), indent=1)
    for n, s in summary.items():
        print(f"{n:18s} PWES {s['pwes_rel_pct'][0]:6.2f} [{s['pwes_rel_pct'][1]:.2f},{s['pwes_rel_pct'][2]:.2f}] crit {s['crit_frac'][0]*100:6.2f} "
              f"reint {s['reint_total'][0]:5.1f} ufls {s['reint_ufls'][0]:4.2f} agg {s['agg_err'][0]:.3f} df {s['df_pilot_mhz'][0]:4.0f}")
    for k, v in tests.items():
        print(k, {a: round(b, 4) for a, b in v.items()})
    print("total", time.time() - t0)


if __name__ == "__main__":
    main()
