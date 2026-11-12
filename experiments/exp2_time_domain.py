"""
Experiment 2 - Time-domain dynamics of the droop channel (choice of chip duration).

Linearised small-signal model of the four grid-forming inverters (P-f droop with
power-measurement low-pass filter, output coupling reactance), coupled through the
Kron-reduced IEEE 33-bus island (loads as constant impedance at the operating point).
A grid-forming inverter knows its own frequency exactly (it is its oscillator state),
so no PLL is needed for listening. We sweep the chip duration and measure (i) the
RCD decoding error caused purely by transients and (ii) the peak frequency excursion.
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from scipy.linalg import expm
from otgfr.network import build_network, droop_gains, MP, F0_HZ
from otgfr.rcd import RCDChannel

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
NET = build_network()
TAU_F = 0.05            # s, power-measurement filter
X_C = 0.15              # pu on inverter rating, coupling reactance
WB = 2 * np.pi * F0_HZ
RAMP = 0.25            # fraction of each chip used for a raised-cosine set-point transition


def reduced_sync_matrix(level=0.6):
    n = NET["n"]; G = len(NET["gfm_bus"])
    Y = NET["Y"].copy()
    yl = (NET["p_nom"] - 1j * NET["q_nom"]) * level      # constant-impedance loads at V=1
    Y[np.diag_indices(n)] += yl
    # add internal inverter nodes
    Yf = np.zeros((n + G, n + G), complex); Yf[:n, :n] = Y
    for g, b in enumerate(NET["gfm_bus"]):
        yc = 1 / (1j * X_C / NET["p_rated"][g])
        i = n + g
        Yf[i, i] += yc; Yf[b, b] += yc; Yf[i, b] -= yc; Yf[b, i] -= yc
    gi = np.arange(n, n + G); li = np.arange(n)
    Yr = Yf[np.ix_(gi, gi)] - Yf[np.ix_(gi, li)] @ np.linalg.solve(Yf[np.ix_(li, li)], Yf[np.ix_(li, gi)])
    B = Yr.imag; Gm = Yr.real
    K = np.zeros((G, G))         # dP_i/dtheta_j at small angle differences, |E|=1
    for i in range(G):
        for j in range(G):
            if i != j:
                K[i, j] = -B[i, j]
        K[i, i] = -K[i].sum()
    return K


def simulate(Tc, L=64, A=0.010, dt=1e-3, soe=None, rng=None, load_sigma=0.0):
    G = len(NET["gfm_bus"])
    D = droop_gains(NET["p_rated"], soe)           # pu P per pu f
    m = 1 / D
    K = reduced_sync_matrix()
    # states: theta (G), Pmeas (G);  w_i = -m_i (Pmeas_i - Pset_i);  P_i = K theta + const
    # dtheta/dt = WB * w ;  dPm/dt = (K theta - Pm)/tau
    Ast = np.zeros((2 * G, 2 * G))
    Ast[:G, G:] = -WB * np.diag(m)
    Ast[G:, :G] = K / TAU_F
    Ast[G:, G:] = -np.eye(G) / TAU_F
    Bst = np.zeros((2 * G, G)); Bst[:G, :] = WB * np.diag(m)          # input: Pset deviation (pilot)
    # integrate input exactly with augmented matrix
    M = np.zeros((3 * G, 3 * G)); M[:2 * G, :2 * G] = Ast; M[:2 * G, 2 * G:] = Bst
    E = expm(M * dt); Ad = E[:2 * G, :2 * G]; Bd = E[:2 * G, 2 * G:]
    ch = RCDChannel([("mean_x", 1.0, False), ("wavg_y", 1.0, True)], length=L, amplitude_mw=A)
    x = rng.uniform(-0.9, 0.9, G); y = rng.uniform(-0.9, 0.9, G); w = rng.uniform(0.05, 1, G)
    truth = dict(mean_x=x.mean(), wavg_y=(w * y).sum() / w.sum())
    P = ch.pilot_powers(ch.contributions(dict(mean_x=x, wavg_y=y), dict(wavg_y=w), dict(wavg_y=1.0)))
    steps = int(round(Tc / dt))
    s = np.zeros(2 * G)
    w_avg = np.zeros((G, L)); wmax = 0.0
    for t in range(L):
        u_new = P[:, t] - (rng.normal(0, load_sigma) * D / D.sum() if load_sigma > 0 else 0)
        u_old = P[:, t - 1] if t > 0 else np.zeros(G)
        acc = np.zeros(G); cnt = 0
        ramp = max(1, int(RAMP * steps))
        for k in range(steps):
            a = 0.5 - 0.5 * np.cos(np.pi * min(k / ramp, 1.0))   # raised-cosine chip edge
            u = u_old + a * (u_new - u_old)
            s = Ad @ s + Bd @ u
            wk = -m * (s[G:] - u)
            wmax = max(wmax, np.abs(wk).max())
            if k >= int(0.5 * steps):         # integrate over the second half of every chip
                acc += wk; cnt += 1
        w_avg[:, t] = acc / cnt
    errs = []
    for g in range(G):
        est = ch.decode(w_avg[g])[0]
        errs.append([est["mean_x"] - truth["mean_x"], est["wavg_y"] - truth["wavg_y"]])
    eig = np.linalg.eigvals(Ast)
    return np.array(errs), wmax * F0_HZ * 1e3, eig


def main():
    rng = np.random.default_rng(2)
    res = {}
    _, _, eig = simulate(1.0, L=8, rng=rng)
    nz = eig[np.abs(eig) > 1e-6]
    res["slowest_mode_time_constant_s"] = float(1 / np.min(-nz.real))
    res["min_damping_ratio"] = float(np.min(-nz.real / np.abs(nz)))
    res["sweep"] = {}
    for Tc in [0.05, 0.1, 0.2, 0.5, 1.0]:
        E = []; pk = []
        for _ in range(15):
            e, wm, _ = simulate(Tc, rng=rng, soe=rng.uniform(0.2, 1, 4))
            E.append(e); pk.append(wm)
        E = np.concatenate(E)
        res["sweep"][str(Tc)] = dict(rmse=float(np.sqrt(np.mean(E ** 2))), peak_df_mhz=float(np.max(pk)))
        print(Tc, res["sweep"][str(Tc)], flush=True)
    # store an example trace for the figure
    json.dump(res, open(os.path.join(OUT, "exp2_time_domain.json"), "w"), indent=2)
    print(res["slowest_mode_time_constant_s"], res["min_damping_ratio"])


if __name__ == "__main__":
    main()
