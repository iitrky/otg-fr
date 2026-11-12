"""
Experiment 1 - Does the AC network compute the weighted average? (validation of RCD)

Chip-by-chip islanded AC droop power flow (Newton, full IEEE 33-bus island, closed ties)
with per-bus stochastic load fluctuation, slow load drift, unknown SoC-adaptive droop gains
and 1 mHz PLL noise at every listening zone. Compares
  (i) the RCD estimate decoded at every zone with the true weighted average,
  (ii) the AC frequency trace with the linear channel model used in Experiment 3.
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from otgfr.network import build_network, droop_powerflow, droop_gains, NQ, F0_HZ
from otgfr.rcd import RCDChannel, linear_channel

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
NET = build_network()
N = 4


def one_round(rng, A_mw, L, load_sigma_frac=0.005, pll_hz=0.001, ac=True):
    ch = RCDChannel([("mean_x", 1.0, False), ("wavg_y", 1.0, True)], length=L, amplitude_mw=A_mw)
    x = rng.uniform(-0.9, 0.9, N); y = rng.uniform(-0.9, 0.9, N); w = rng.uniform(0.05, 1.0, N)
    truth = dict(mean_x=x.mean(), wavg_y=(w * y).sum() / w.sum())
    Z = ch.contributions(dict(mean_x=x, wavg_y=y), dict(wavg_y=w), dict(wavg_y=1.0))
    P = ch.pilot_powers(Z)                                    # N x L (MW = pu)
    level = rng.uniform(0.35, 0.9)
    bus_f = rng.uniform(0.7, 1.3, NET["n"])
    pl = NET["p_nom"] * level * bus_f; ql = NET["q_nom"] * level * bus_f
    pv = np.zeros(NET["n"])
    pv[NET["gfm_bus"]] = NET["pv_rated"] * rng.uniform(0, 0.8)
    soe = rng.uniform(0.2, 1.0, N)
    D = droop_gains(NET["p_rated"], soe)                      # unknown to every zone
    nq = NQ * NET["p_rated"]
    net_load = pl.sum() - pv.sum()
    p_base = D / D.sum() * (net_load + 0.02)                  # secondary set-points (held)
    dw = np.zeros(L); dw_lin = np.zeros(L); x0 = None
    drift = rng.normal() * 0.01
    fl_tot = np.zeros(L)
    for t in range(L):
        # independent per-bus fluctuations; island-total std = load_sigma_frac * total load
        fl = rng.normal(0, 1, NET["n"]) * pl * load_sigma_frac * pl.sum() / np.sqrt((pl ** 2).sum())
        dr = drift * (2 * t / (L - 1) - 1) * pl / pl.sum()
        fl_tot[t] = fl.sum() + dr.sum()
        if ac:
            r = droop_powerflow(NET["Y"], NET["gfm_bus"], p_base + P[:, t], D, nq, pl + fl + dr, ql * (1 + fl / np.maximum(pl, 1e-9)),
                                pv, x0=x0)
            x0 = r["x"]; dw[t] = r["dw"]
    # linear model: dw = (sum p_base + pilots - load - losses)/sum D, losses taken at the round's mean
    dw_lin = (p_base.sum() + P.sum(0) - (pl.sum() + fl_tot - pv.sum())) / D.sum()
    if ac:
        dw_lin = dw_lin - (dw_lin.mean() - dw.mean())          # common loss offset
    meas = (dw if ac else dw_lin)[None, :] + rng.normal(0, pll_hz / F0_HZ, (N, L))
    est = [ch.decode(meas[k])[0] for k in range(N)]
    err = {q: [e[q] - truth[q] for e in est] for q in truth}
    out = dict(err_mean=np.array(err["mean_x"]), err_wavg=np.array(err["wavg_y"]),
               pair=[truth["mean_x"], est[0]["mean_x"], truth["wavg_y"], est[0]["wavg_y"]],
               max_pilot_df_mhz=float(np.max(np.abs(P.sum(0) / D.sum())) * F0_HZ * 1e3),
               max_pilot_frac=float(np.max(np.abs(P)) / NET["p_rated"].min()))
    if ac:
        out["lin_vs_ac_rmse_mhz"] = float(np.sqrt(np.mean((dw - dw_lin) ** 2)) * F0_HZ * 1e3)
        out["df_std_mhz"] = float(np.std(dw) * F0_HZ * 1e3)
    return out


def summarize(rs, key):
    e = np.concatenate([r[key] for r in rs])
    return dict(rmse=float(np.sqrt(np.mean(e ** 2))), p95=float(np.percentile(np.abs(e), 95)))


def main():
    t0 = time.time()
    res = {}
    rng = np.random.default_rng(1)
    # (a) AC power flow, amplitude sweep at L = 64
    res["ac_amplitude"] = {}
    for A in [0.002, 0.005, 0.010, 0.020]:
        rs = [one_round(rng, A, 64, ac=True) for _ in range(60)]
        res["ac_amplitude"][f"{A*1e3:.0f}kW"] = dict(
            mean=summarize(rs, "err_mean"), wavg=summarize(rs, "err_wavg"),
            lin_vs_ac_rmse_mhz=float(np.mean([r["lin_vs_ac_rmse_mhz"] for r in rs])),
            max_pilot_df_mhz=float(np.max([r["max_pilot_df_mhz"] for r in rs])),
            max_pilot_frac_of_smallest_rating=float(np.max([r["max_pilot_frac"] for r in rs])),
            pairs=[[float(v) for v in r["pair"]] for r in rs])
        print("AC", A, res["ac_amplitude"][f"{A*1e3:.0f}kW"], f"{time.time()-t0:.0f}s", flush=True)
    # (b) linear model, same sweep (checks the model used in Exp. 3)
    res["lin_amplitude"] = {}
    for A in [0.002, 0.005, 0.010, 0.020]:
        rs = [one_round(rng, A, 64, ac=False) for _ in range(400)]
        res["lin_amplitude"][f"{A*1e3:.0f}kW"] = dict(mean=summarize(rs, "err_mean"), wavg=summarize(rs, "err_wavg"))
    # (c) code length sweep (linear), A = 10 kW
    res["lin_length"] = {}
    for L in [16, 32, 64, 128, 256]:
        rs = [one_round(rng, 0.010, L, ac=False) for _ in range(400)]
        res["lin_length"][str(L)] = dict(mean=summarize(rs, "err_mean"), wavg=summarize(rs, "err_wavg"))
    # (d) load-noise sweep (linear), A = 10 kW, L = 64
    res["lin_noise"] = {}
    for s in [0.0025, 0.005, 0.01, 0.02]:
        rs = [one_round(rng, 0.010, 64, load_sigma_frac=s, ac=False) for _ in range(400)]
        res["lin_noise"][f"{s*100:.2f}%"] = dict(mean=summarize(rs, "err_mean"), wavg=summarize(rs, "err_wavg"))
    json.dump(res, open(os.path.join(OUT, "exp1_channel_validation.json"), "w"), indent=2)
    print(json.dumps(res["lin_length"], indent=1), json.dumps(res["lin_noise"], indent=1))
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
