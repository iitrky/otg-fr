"""
Experiment 3 - Closed-loop 24-h restoration Monte Carlo (100 scenarios).
Writes results/otg/exp3_restoration.json (per-scenario metrics and paired statistics).
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
    "full_info": ("full_info", {}),
    "local_rating": ("local_rating", {}),
    "local_soc": ("local_soc", {}),
    **{f"telecom_p{p:.2f}": ("telecom", dict(p_link=p)) for p in [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]},
    "otg": ("otg", {}),
    **{f"otg_dp{s:.2f}": ("otg_dp", dict(dp_sigma=s)) for s in [0.05, 0.10, 0.20]},
    "otg_noise1%": ("otg", dict(load_sigma_frac=0.01)),
    "otg_noise2%": ("otg", dict(load_sigma_frac=0.02)),
    "otg_L64": ("otg", dict(otg_len=64)),
    "otg_no_clpu_fusion": ("otg", dict(fuse_clpu=False)),
}
KEYS = ["pwes", "crit_frac", "energy", "reint_planned", "reint_ufls", "reint_total", "vmin", "vmax",
        "df_pilot_mhz", "min_soe", "agg_err"]


def one(seed):
    scn = make_scenario(seed)
    out = {}
    for name, (m, kw) in CONFIGS.items():
        L = run(scn, m, **kw)
        out[name] = {k: float(L[k]) for k in KEYS}
        out[name]["clpu_err_final"] = float(np.mean(L["clpu_err"][-48:]))
        if seed == 0:
            out[name]["trace"] = dict(lam=L["lam"], soe=L["soe"], served_mw=L["served_mw"], clpu_err=L["clpu_err"])
    out["_scn"] = dict(m=float(scn["m_true"]), tau=float(scn["t_true"]), day=float(scn["day"]))
    return out


def ci(x):
    x = np.asarray(x); m = x.mean(); h = 1.96 * x.std(ddof=1) / np.sqrt(len(x))
    return [float(m), float(m - h), float(m + h)]


def main():
    t0 = time.time()
    with Pool(4) as pool:
        per = pool.map(one, range(N_SCEN))
    print("simulated", time.time() - t0)
    summary = {}
    ref = np.array([p["full_info"]["pwes"] for p in per])
    for name in CONFIGS:
        rel = np.array([p[name]["pwes"] for p in per]) / ref * 100
        summary[name] = dict(pwes_rel_pct=ci(rel), **{k: ci([p[name][k] for p in per]) for k in KEYS + ["clpu_err_final"]})
    tests = {}
    for a, b in [("otg", "local_soc"), ("otg", "local_rating"), ("otg", "telecom_p0.50"), ("otg", "telecom_p0.75"),
                 ("otg", "telecom_p0.90"), ("otg", "telecom_p1.00"), ("otg", "otg_no_clpu_fusion"),
                 ("otg", "otg_dp0.10")]:
        for k in ["pwes", "crit_frac", "reint_total"]:
            x = np.array([p[a][k] for p in per]); y = np.array([p[b][k] for p in per])
            d = x - y
            w = stats.wilcoxon(x, y) if np.any(d != 0) else None
            tests[f"{a}_vs_{b}_{k}"] = dict(mean_diff=float(d.mean()), wins=int((d > 0).sum()), losses=int((d < 0).sum()),
                                           p_wilcoxon=float(w.pvalue) if w else 1.0)
    json.dump(dict(summary=summary, tests=tests, per_scenario=per), open(os.path.join(OUT, "exp3_restoration.json"), "w"))
    for n, s in summary.items():
        print(f"{n:22s} PWES% {s['pwes_rel_pct'][0]:6.2f} [{s['pwes_rel_pct'][1]:.2f},{s['pwes_rel_pct'][2]:.2f}]  crit {s['crit_frac'][0]*100:6.2f}"
              f"  reint {s['reint_total'][0]:6.1f} ufls {s['reint_ufls'][0]:5.2f}  vmin {s['vmin'][0]:.3f} df {s['df_pilot_mhz'][0]:5.0f} clpu {s['clpu_err_final'][0]:.3f}")
    for k, v in tests.items():
        print(k, v)
    print("total", time.time() - t0)


if __name__ == "__main__":
    main()
