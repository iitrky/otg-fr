"""
Experiment 8 - Statistical analysis of the closed-loop comparisons (Experiment 3).

For every pre-registered comparison of OTG-FR with a baseline or ablation, on the 100 paired scenarios:
  * mean paired difference with a 95 % percentile-bootstrap confidence interval (10 000 resamples),
  * Hodges-Lehmann estimate of the median paired difference,
  * matched-pairs rank-biserial correlation r (effect size of the Wilcoxon signed-rank test),
  * two-sided Wilcoxon signed-rank p-value and Holm-Bonferroni adjusted p-value over the whole family.
"""
import os, json
import numpy as np
from scipy import stats

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
COMPARISONS = [("otg", b) for b in ["local_soc", "local_rating", "telecom_p0.50", "telecom_p0.75", "telecom_p0.90",
                                     "telecom_p1.00", "otg_v1", "otg_no_price_avg", "otg_sequency_codes",
                                     "otg_no_clpu_fusion", "otg_dp0.10"]]
METRICS = ["pwes_rel", "crit_pct", "reint_total"]


def rank_biserial(d):
    d = d[d != 0]
    if len(d) == 0:
        return 0.0
    r = stats.rankdata(np.abs(d))
    return float((r[d > 0].sum() - r[d < 0].sum()) / r.sum())


def hodges_lehmann(d):
    w = (d[:, None] + d[None, :]) / 2
    return float(np.median(w[np.triu_indices(len(d))]))


def main():
    E = json.load(open(os.path.join(R, "exp3_restoration.json")))
    per = E["per_scenario"]
    ref = np.array([p["full_info"]["pwes"] for p in per])
    get = lambda n, m: (np.array([p[n]["pwes"] for p in per]) / ref * 100 if m == "pwes_rel" else
                        np.array([p[n]["crit_frac"] for p in per]) * 100 if m == "crit_pct" else
                        np.array([p[n][m] for p in per]))
    rng = np.random.default_rng(8)
    rows = []
    for a, b in COMPARISONS:
        for m in METRICS:
            d = get(a, m) - get(b, m)
            boot = d[rng.integers(0, len(d), (10000, len(d)))].mean(1)
            p = float(stats.wilcoxon(d).pvalue) if np.any(d != 0) else 1.0
            rows.append(dict(a=a, b=b, metric=m, mean_diff=float(d.mean()), ci=[float(np.percentile(boot, 2.5)),
                        float(np.percentile(boot, 97.5))], hl=hodges_lehmann(d), r_rb=rank_biserial(d),
                        wins=int((d > 0).sum()), losses=int((d < 0).sum()), p=p))
    # Holm-Bonferroni over the whole family
    order = np.argsort([r["p"] for r in rows]); m = len(rows); running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * rows[i]["p"]))
        rows[i]["p_holm"] = running
    json.dump(dict(n_scenarios=len(per), family_size=m, rows=rows), open(os.path.join(R, "exp8_statistics.json"), "w"), indent=1)
    for r in rows:
        print(f"{r['a']} vs {r['b']:20s} {r['metric']:12s} diff {r['mean_diff']:8.3f} CI [{r['ci'][0]:.3f},{r['ci'][1]:.3f}] "
              f"HL {r['hl']:7.3f} r_rb {r['r_rb']:6.3f} W/L {r['wins']}/{r['losses']} p {r['p']:.2e} p_holm {r['p_holm']:.2e}")


if __name__ == "__main__":
    main()
