"""
Experiment 6 - Comparison with the closest prior art: power talk (droop-set-point signalling).

Four aggregation schemes over the same droop channel, factorial in two design choices:
                         assumed stiffness (D_nom)        ratio decoding (invariant)
  time-slotted (TDMA)    PT-TDMA  (power talk [angj])     PT-TDMA+ratio
  simultaneous (coded)   CDMA-direct                      RCD (proposed)
TDMA: zone k signals alone in slot k (L/N chips) on short Walsh codes; every listener decodes each
zone's values and averages them itself (per-zone values are exposed). CDMA: all zones signal at
once on length-L codes; the network forms the sum.
Conditions: (i) stiffness known (no SoC scaling), (ii) SoC-adaptive stiffness unknown to the zones,
(iii) as (ii) plus an inverter trip half-way through the round (-30 % stiffness, tripped unit silent).
Fairness: equal round length L*Tc and equal peak frequency excursion (amplitude of each scheme
calibrated so that its 95th-percentile pilot excursion is 50 mHz).
Outputs: RMSE of the island mean and weighted mean versus N, the round length each scheme needs
to reach RMSE <= 0.1, and an AC power-flow check on the IEEE 33-bus island (N = 4).
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from otgfr.rcd import walsh_codes
from otgfr.network import build_network, droop_powerflow, droop_gains, NQ

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
NET = build_network()
F0, PLL_HZ, MP = 60.0, 0.001, 0.02
SCHEMES = ["PT-TDMA", "PT-TDMA+ratio", "CDMA-direct", "RCD"]
TARGET_MHZ = 50.0


def draw(rng, N):
    x = rng.uniform(-0.9, 0.9, N); y = rng.uniform(-0.9, 0.9, N); w = rng.uniform(0.05, 1.0, N)
    p_r = NET["p_rated"].copy() if N == 4 else rng.uniform(0.4, 1.6, N)
    return x, y, w, p_r


def pilots(scheme, A, L, x, y, w):
    """Return pilot matrix N x L and a decoder f(dw, D_nom) -> (mean, wavg)."""
    N = len(x)
    if scheme in ("RCD", "CDMA-direct"):
        C = walsh_codes(4, L, order="drift")          # ones, x, w*y, w
        Z = np.stack([np.full(N, 0.5), 0.5 * x, w * y, w], 1)
        P = A * Z @ C

        def dec(dw, D_nom):
            yc = C @ dw / L
            if scheme == "RCD":
                return yc[1] / yc[0], yc[2] / yc[3]
            g = D_nom / A                                 # assumed channel gain
            return yc[1] * g / (0.5 * N), (yc[2] * g) / (yc[3] * g)
        return P, dec
    Ls = L // N
    ncode = 3 if scheme == "PT-TDMA" else 4
    if Ls - 1 < ncode:
        return None, None
    C = walsh_codes(3 if scheme == "PT-TDMA" else 4, Ls, order="drift")
    P = np.zeros((N, L))
    for k in range(N):
        zk = np.array([0.5 * x[k], w[k] * y[k], w[k]] + ([0.5] if scheme == "PT-TDMA+ratio" else []))
        P[k, k * Ls:(k + 1) * Ls] = A * zk @ C

    def dec(dw, D_nom):
        xs, wy, ws = np.zeros(N), np.zeros(N), np.zeros(N)
        for k in range(N):
            yc = C @ dw[k * Ls:(k + 1) * Ls] / Ls
            g = (0.5 / yc[3]) if scheme == "PT-TDMA+ratio" else D_nom / A
            xs[k], wy[k], ws[k] = yc[0] * g / 0.5, yc[1] * g, yc[2] * g
        return xs.mean(), wy.sum() / ws.sum()
    return P, dec


def lin_round(rng, scheme, A, L, N, cond, sig_frac=0.005):
    x, y, w, p_r = draw(rng, N)
    P, dec = pilots(scheme, A, L, x, y, w)
    if P is None:
        return None
    D_nom = (p_r / MP).sum()
    soe = np.ones(N) if cond == "known" else rng.uniform(0.2, 1.0, N)
    Dk = p_r / MP * soe
    Dt = np.full(L, Dk.sum())
    if cond == "trip":
        Dt[L // 2:] = 0.7 * Dk.sum(); P = P.copy(); P[0, L // 2:] = 0.0
    load = 0.6 * p_r.sum()
    dw = (P.sum(0) - rng.normal(0, sig_frac * load, L) - 0.01 * np.linspace(-1, 1, L) * rng.normal()) / Dt \
        + rng.normal(0, PLL_HZ / F0, L)
    m, wa = dec(dw, D_nom)
    return np.array([m - x.mean(), wa - (w * y).sum() / w.sum()]), np.abs(P.sum(0) / Dt).max() * F0 * 1e3


def calibrate(rng, scheme, L, N):
    """Amplitude giving a 95th-percentile pilot excursion of TARGET_MHZ (nominal stiffness)."""
    pk = []
    for _ in range(200):
        x, y, w, p_r = draw(rng, N)
        P, _ = pilots(scheme, 1.0, L, x, y, w)
        if P is None:
            return None
        pk.append(np.abs(P.sum(0)).max() / (p_r / MP * rng.uniform(0.2, 1.0, N)).sum() * F0 * 1e3)
    return TARGET_MHZ / np.percentile(pk, 95)


def rmse_point(rng, scheme, L, N, cond, n=300):
    A = calibrate(rng, scheme, L, N)
    if A is None:
        return None
    R = [lin_round(rng, scheme, A, L, N, cond) for _ in range(n)]
    E = np.array([r[0] for r in R])
    E = np.where(np.isfinite(E), E, 10.0)
    return dict(A_kw=float(A * 1e3), rmse_mean=float(np.sqrt(np.mean(E[:, 0] ** 2))),
                rmse_wavg=float(np.sqrt(np.mean(E[:, 1] ** 2))),
                medae_mean=float(np.median(np.abs(E[:, 0]))), peak_p95_mhz=float(np.percentile([r[1] for r in R], 95)))


def ac_round(rng, scheme, L=128, A=None):
    N = 4
    x, y, w, p_r = draw(rng, N)
    P, dec = pilots(scheme, A, L, x, y, w)
    level = rng.uniform(0.35, 0.9); bus_f = rng.uniform(0.7, 1.3, NET["n"])
    pl = NET["p_nom"] * level * bus_f; ql = NET["q_nom"] * level * bus_f
    pv = np.zeros(NET["n"]); pv[NET["gfm_bus"]] = NET["pv_rated"] * rng.uniform(0, 0.8)
    soe = rng.uniform(0.2, 1.0, N); D = droop_gains(NET["p_rated"], soe); nq = NQ * NET["p_rated"]
    p_base = D / D.sum() * (pl.sum() - pv.sum() + 0.02)
    dw = np.zeros(L); x0 = None
    for t in range(L):
        fl = rng.normal(0, 1, NET["n"]) * pl * 0.005 * pl.sum() / np.sqrt((pl ** 2).sum())
        r = droop_powerflow(NET["Y"], NET["gfm_bus"], p_base + P[:, t], D, nq, pl + fl, ql, pv, x0=x0)
        x0 = r["x"]; dw[t] = r["dw"]
    m, wa = dec(dw + rng.normal(0, PLL_HZ / F0, L), (NET["p_rated"] / MP).sum())
    return np.array([m - x.mean(), wa - (w * y).sum() / w.sum()])


def main():
    t0 = time.time()
    rng = np.random.default_rng(6)
    res = {"vs_N": {}, "latency": {}, "ac": {}}
    for cond in ["known", "soc_unknown", "trip"]:
        res["vs_N"][cond] = {}
        for sc in SCHEMES:
            res["vs_N"][cond][sc] = {str(N): rmse_point(rng, sc, 128, N, cond) for N in [4, 8, 16, 32, 64]}
            print(cond, sc, {N: (round(v["rmse_mean"], 3), round(v["rmse_wavg"], 3)) if v else None
                             for N, v in res["vs_N"][cond][sc].items()}, f"{time.time()-t0:.0f}s", flush=True)
    # round length (chips = seconds at Tc = 1 s) needed for RMSE(mean) <= 0.1, SoC-adaptive stiffness unknown
    for sc in SCHEMES:
        res["latency"][sc] = {}
        for N in [4, 8, 16, 32, 64]:
            need = None
            for L in [32, 64, 128, 256, 512, 1024, 2048, 4096]:
                p = rmse_point(rng, sc, L, N, "soc_unknown", n=200)
                if p and p["rmse_mean"] <= 0.1:
                    need = L; break
            res["latency"][sc][str(N)] = need
        print("latency", sc, res["latency"][sc], f"{time.time()-t0:.0f}s", flush=True)
    # AC power-flow check, N = 4, L = 128, stiffness unknown
    for sc in SCHEMES:
        A = calibrate(rng, sc, 128, 4)
        E = np.array([ac_round(rng, sc, 128, A) for _ in range(60)])
        res["ac"][sc] = dict(rmse_mean=float(np.sqrt(np.mean(E[:, 0] ** 2))), rmse_wavg=float(np.sqrt(np.mean(E[:, 1] ** 2))),
                             A_kw=float(A * 1e3))
        print("AC", sc, res["ac"][sc], f"{time.time()-t0:.0f}s", flush=True)
    json.dump(res, open(os.path.join(OUT, "exp6_powertalk.json"), "w"), indent=2)
    print("done", time.time() - t0)


if __name__ == "__main__":
    main()
