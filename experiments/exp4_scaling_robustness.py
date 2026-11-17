"""
Experiment 4 - Scalability with the number of zones and robustness to an inverter trip.

(a) N grid-forming zones (4..64) share one island; aggregate droop stiffness grows with N.
    The RCD round length is fixed (64 or 128 chips) whatever N, whereas a polled telecom
    protocol needs N uplink slots.
(b) One inverter trips half-way through a round (sum of droop gains falls by 30 %).
    Ratio decoding is compared with naive decoding that assumes a known stiffness.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from otgfr.rcd import RCDChannel, zcdp_epsilon

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
F0 = 60.0


def round_err(rng, N, L=128, A=0.006, trip=False, load_sigma_frac=0.005, naive=False):
    ch = RCDChannel([("mean_x", 1.0, False), ("wavg_y", 1.0, True)], length=L, amplitude_mw=A)
    x = rng.uniform(-0.9, 0.9, N); y = rng.uniform(-0.9, 0.9, N); w = rng.uniform(0.05, 1, N)
    truth = np.array([x.mean(), (w * y).sum() / w.sum()])
    P = ch.pilot_powers(ch.contributions(dict(mean_x=x, wavg_y=y), dict(wavg_y=w), dict(wavg_y=1.0)))
    p_rated = rng.uniform(0.4, 1.6, N)
    D = p_rated / 0.02 * rng.uniform(0.2, 1, N)
    load = 0.6 * p_rated.sum()
    Dt = np.full(L, D.sum())
    if trip:
        Dt[L // 2:] = D.sum() * 0.7
        P = P.copy(); P[0, L // 2:] = 0.0               # tripped inverter stops piloting
    dw = (P.sum(0) - rng.normal(0, load_sigma_frac * load, L)) / Dt + rng.normal(0, 0.001 / F0, L)
    est, ycorr = ch.decode(dw)
    if naive:   # assumes the pre-event stiffness is known and divides by it
        e = np.array([ycorr[ch.num_code["mean_x"]] * D.sum() / (A * 0.5 * N) * 1.0,
                      np.nan])
        return np.abs(e[0] - truth[0])
    e = np.array([est["mean_x"], est["wavg_y"]])
    if trip:   # truth after trip: zone 0 contributes half the chips -> compare with time-weighted truth
        pass
    return np.abs(e - truth)


def main():
    rng = np.random.default_rng(4)
    res = {"scaling": {}, "trip": {}}
    for N in [4, 8, 16, 32, 64]:
        E = np.array([round_err(rng, N) for _ in range(400)])
        res["scaling"][str(N)] = dict(mae_mean=float(E[:, 0].mean()), mae_wavg=float(E[:, 1].mean()),
                                      rcd_round_s=128, telecom_polled_slots=N)
    for trip in [False, True]:
        E = np.array([round_err(rng, 8, trip=trip) for _ in range(400)])
        En = np.array([round_err(rng, 8, trip=trip, naive=True) for _ in range(400)])
        res["trip"]["trip" if trip else "no_trip"] = dict(ratio_mae_mean=float(E[:, 0].mean()),
                                                          ratio_mae_wavg=float(E[:, 1].mean()),
                                                          naive_mae_mean=float(En.mean()))
    # privacy accounting of the dither (per quantity, per round, sensitivity 1 in code units)
    res["dp"] = {f"{s:.2f}": dict(eps_per_round=float(zcdp_epsilon(1.0, s, 1)),
                                  eps_24h_288_rounds=float(zcdp_epsilon(1.0, s, 288)),
                                  eps_24h_480_rounds=float(zcdp_epsilon(1.0, s, 480))) for s in [0.05, 0.1, 0.2, 0.5, 1.0]}   # 96 steps x R rounds
    json.dump(res, open(os.path.join(OUT, "exp4_scaling_robustness.json"), "w"), indent=2)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
