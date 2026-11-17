"""
Experiment 5 - Verification of the analytical results of Section 3.4.

(a) Proposition 3 (decoding error): the closed-form RMSE
        RMSE ~= s * sqrt(sigma_e^2 + D^2 sigma_n^2) / (A * S_den * sqrt(L)) * sqrt(1 + xbar^2)
    is compared with Monte Carlo RMSE over code length L, pilot amplitude A, chip-level load
    noise sigma_e and number of zones N (linear channel, 400 rounds per point).
(b) Proposition 2 (drift rejection): decoding error under a deterministic net-load ramp of
    0-1 MW per round (linear + quadratic part, e.g. a cloud edge on the PV park) for the v1.0
    sequency-ordered codes and the proposed drift-ordered codes, in the linear channel and in
    chip-by-chip AC droop power flow on the IEEE 33-bus island.
(c) Proposition 4 (excursion bound): observed peak pilot excursion versus the bound.
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from otgfr.rcd import RCDChannel, code_drift_order, walsh_codes
from otgfr.network import build_network, droop_powerflow, droop_gains, NQ, F0_HZ

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
NET = build_network()
F0 = 60.0
PLL_HZ = 0.001


def predicted_rmse(A, L, N, sig_e, D, x, w):
    """Proposition 3, evaluated per round. Returns (mean, weighted mean) predicted std."""
    sig_y = np.sqrt(sig_e ** 2 + (D * PLL_HZ / F0) ** 2) / np.sqrt(L)       # MW-equivalent per code
    xbar = x.mean(); wbar = (w * x).sum() / w.sum()
    s_mean = sig_y / (A * 0.5 * N) * np.sqrt(1 + xbar ** 2)
    s_w = sig_y / (A * w.sum()) * np.sqrt(1 + wbar ** 2)
    return s_mean, s_w


def lin_round(rng, A, L, N, sig_frac, order="drift", ramp=0.0, curv=0.0):
    ch = RCDChannel([("mean_x", 1.0, False), ("wavg_y", 1.0, True)], length=L, amplitude_mw=A, code_order=order)
    x = rng.uniform(-0.9, 0.9, N); y = rng.uniform(-0.9, 0.9, N); w = rng.uniform(0.05, 1.0, N)
    P = ch.pilot_powers(ch.contributions(dict(mean_x=x, wavg_y=y), dict(wavg_y=w), dict(wavg_y=1.0)))
    p_r = rng.uniform(0.4, 1.6, N) if N != 4 else NET["p_rated"]
    D = (p_r / 0.02 * rng.uniform(0.2, 1.0, N)).sum()
    load = 0.6 * p_r.sum()
    sig_e = sig_frac * load
    u = np.linspace(-1, 1, L)
    e = rng.normal(0, sig_e, L) + 0.5 * ramp * u + curv * (u ** 2 - np.mean(u ** 2))
    dw = (P.sum(0) - e) / D + rng.normal(0, PLL_HZ / F0, L)
    est = ch.decode(dw)[0]
    err = np.array([est["mean_x"] - x.mean(), est["wavg_y"] - (w * y).sum() / w.sum()])
    pred = np.array(predicted_rmse(A, L, N, sig_e, D, x, w))
    peak = np.abs(P.sum(0)).max() / D * F0 * 1e3
    bound = A * np.abs(ch.contributions(dict(mean_x=x, wavg_y=y), dict(wavg_y=w), dict(wavg_y=1.0)).sum(0)).sum() / D * F0 * 1e3
    return err, pred, peak, bound


def sweep(rng, name, values, make, n=400):
    out = {}
    for v in values:
        E, Pr, pk, bd = [], [], [], []
        for _ in range(n):
            e, p, a, b = make(v)
            E.append(e); Pr.append(p); pk.append(a); bd.append(b)
        E = np.array(E); Pr = np.array(Pr)
        out[str(v)] = dict(sim_rmse_mean=float(np.sqrt(np.mean(E[:, 0] ** 2))), sim_rmse_wavg=float(np.sqrt(np.mean(E[:, 1] ** 2))),
                           pred_rmse_mean=float(np.sqrt(np.mean(Pr[:, 0] ** 2))), pred_rmse_wavg=float(np.sqrt(np.mean(Pr[:, 1] ** 2))),
                           peak_mhz_max=float(np.max(pk)), bound_violations=int(np.sum(np.array(pk) > np.array(bd) + 1e-9)))
        print(name, v, {k: round(x, 4) for k, x in out[str(v)].items()}, flush=True)
    return out


def ac_ramp_round(rng, ramp_mw, order, L=128, A=0.006, noise=True):
    """Chip-by-chip AC droop power flow with a net-load ramp applied at the PV park (bus 16)."""
    ch = RCDChannel([("mean_x", 1.0, False), ("wavg_y", 1.0, True)], length=L, amplitude_mw=A, code_order=order)
    N = 4
    x = rng.uniform(-0.9, 0.9, N); y = rng.uniform(-0.9, 0.9, N); w = rng.uniform(0.05, 1.0, N)
    P = ch.pilot_powers(ch.contributions(dict(mean_x=x, wavg_y=y), dict(wavg_y=w), dict(wavg_y=1.0)))
    level = rng.uniform(0.35, 0.9)
    pl = NET["p_nom"] * level; ql = NET["q_nom"] * level
    soe = rng.uniform(0.2, 1.0, N); D = droop_gains(NET["p_rated"], soe); nq = NQ * NET["p_rated"]
    pv0 = np.zeros(NET["n"]); pv0[NET["gfm_bus"]] = NET["pv_rated"] * 0.5
    p_base = D / D.sum() * (pl.sum() - pv0.sum() + 0.02)
    u = np.linspace(-1, 1, L); x0 = None; dw = np.zeros(L)
    for t in range(L):
        fl = rng.normal(0, 1, NET["n"]) * pl * 0.005 * pl.sum() / np.sqrt((pl ** 2).sum()) * noise
        pv = pv0.copy()
        pv[NET["gfm_bus"][2]] += -0.5 * ramp_mw * u[t] + 0.25 * ramp_mw * (u[t] ** 2 - 1 / 3)   # cloud edge on PV park
        r = droop_powerflow(NET["Y"], NET["gfm_bus"], p_base + P[:, t], D, nq, pl + fl, ql, pv, x0=x0)
        x0 = r["x"]; dw[t] = r["dw"]
    meas = dw + rng.normal(0, PLL_HZ / F0, L) * noise
    est = ch.decode(meas)[0]
    return abs(est["mean_x"] - x.mean()), abs(est["wavg_y"] - (w * y).sum() / w.sum())


def main():
    t0 = time.time()
    rng = np.random.default_rng(5)
    res = dict(code_drift_order=dict(sequency=code_drift_order(walsh_codes(13, 128, "sequency")),
                                     drift=code_drift_order(walsh_codes(13, 128, "drift"))))
    # (a) Proposition 3
    res["prop3_L"] = sweep(rng, "L", [16, 32, 64, 128, 256], lambda L: lin_round(rng, 0.010, L, 4, 0.005))
    res["prop3_A"] = sweep(rng, "A", [0.002, 0.005, 0.010, 0.020], lambda A: lin_round(rng, A, 64, 4, 0.005))
    res["prop3_noise"] = sweep(rng, "noise", [0.0025, 0.005, 0.01, 0.02], lambda s: lin_round(rng, 0.010, 64, 4, s))
    res["prop3_N"] = sweep(rng, "N", [4, 8, 16, 32, 64], lambda N: lin_round(rng, 0.006, 128, N, 0.005))
    pairs = [(v["pred_rmse_mean"], v["sim_rmse_mean"]) for k in ("prop3_L", "prop3_A", "prop3_noise", "prop3_N")
             for v in res[k].values()] + [(v["pred_rmse_wavg"], v["sim_rmse_wavg"]) for k in ("prop3_L", "prop3_A", "prop3_noise", "prop3_N")
                                          for v in res[k].values()]
    pr, sm = np.array(pairs).T
    res["prop3_fit"] = dict(n_points=len(pr), median_ratio_sim_over_pred=float(np.median(sm / pr)),
                            max_abs_rel_dev=float(np.max(np.abs(sm / pr - 1))),
                            r2_log=float(1 - np.sum((np.log(sm) - np.log(pr)) ** 2) / np.sum((np.log(sm) - np.log(sm).mean()) ** 2)))
    print("fit", res["prop3_fit"], flush=True)
    # (b) Proposition 2, linear channel
    res["prop2_lin"] = {}
    for order in ["sequency", "drift"]:
        res["prop2_lin"][order] = sweep(rng, "ramp-" + order, [0.0, 0.05, 0.1, 0.25, 0.5, 1.0],
                                        lambda R: lin_round(rng, 0.006, 128, 4, 0.005, order=order, ramp=R, curv=0.5 * R), n=300)
    # (b) Proposition 2, AC power flow
    # noise-free AC rounds isolate the deterministic ramp-induced error; noisy rounds give the total error
    res["prop2_ac"] = {}
    for noise, n in [(False, 20), (True, 120)]:
        for R in [0.0, 0.25, 0.5, 1.0]:
            for order in ["sequency", "drift"]:
                E = np.array([ac_ramp_round(rng, R, order, noise=noise) for _ in range(n)])
                key = f"{'noisy' if noise else 'noisefree'}_{order}_{R}"
                res["prop2_ac"][key] = dict(rmse_mean=float(np.sqrt((E[:, 0] ** 2).mean())), rmse_wavg=float(np.sqrt((E[:, 1] ** 2).mean())),
                                            max_mean=float(E[:, 0].max()))
                print("AC ramp", key, res["prop2_ac"][key], f"{time.time()-t0:.0f}s", flush=True)
    # validity of Proposition 3: points with predicted RMSE <= 0.2 (denominator SNR >= ~5)
    ok = pr <= 0.2
    res["prop3_fit_valid_regime"] = dict(n_points=int(ok.sum()), max_abs_rel_dev=float(np.max(np.abs(sm[ok] / pr[ok] - 1))),
                                         mean_abs_rel_dev=float(np.mean(np.abs(sm[ok] / pr[ok] - 1))))
    print("valid-regime fit", res["prop3_fit_valid_regime"], flush=True)
    json.dump(res, open(os.path.join(OUT, "exp5_theory.json"), "w"), indent=2)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
