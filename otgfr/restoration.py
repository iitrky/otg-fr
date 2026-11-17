"""
Algorithm 1 - Over-the-Grid Federated Restoration (OTG-FR) and baselines.

A 24-hour restoration of the islanded IEEE 33-bus feeder (start 18:00, 15-min steps)
after an upstream black-out with telecom outages. Four zones own grid-forming battery
inverters and PV. Each zone decides which of its load blocks (one per bus) to energise.
Coupling between zones is physical: the battery energy of the whole island is shared
through droop, so a zone's decision changes everyone's energy budget. The cold-load
pick-up (CLPU) behaviour of re-energised load is unknown and learned from each zone's
own telemetry.

Methods (all share the same scenario, load, PV, CLPU and noise realisations):
  full_info      centralised planner, perfect communication, true CLPU, perfect PV forecast
  local_rating   each zone plans alone; classical rating-proportional droop sharing
  local_soc      each zone plans alone; SoC-adaptive droop sharing (communication-free SOTA)
  telecom_p      the proposed federated planner, aggregates exchanged over a telecom network
                 whose per-zone link availability is p (Markov outages, mean 2 h)
  otg            proposed: aggregates computed by the power network itself (Algorithm 2)
  otg_dp         proposed with Gaussian dither for differential privacy
"""
import numpy as np
from .network import build_network, droop_powerflow, droop_gains, NQ, F0_HZ, N_ZONES
from .rcd import RCDChannel, linear_channel

NET = build_network()
DT = 0.25
STEPS = 96
H0 = 18.0
SOE_MIN = 0.05
ETA = 0.95
CLASS_W = {"critical": 10.0, "essential": 3.0, "normal": 1.0}
G_HOURLY = np.array([0.62, 0.58, 0.56, 0.55, 0.57, 0.63, 0.72, 0.80, 0.83, 0.84, 0.85, 0.86,
                     0.86, 0.85, 0.84, 0.85, 0.90, 0.97, 1.00, 0.99, 0.95, 0.88, 0.78, 0.69])
CHECKPOINTS_H = [2, 6, 10, 14, 24]
M_GRID = np.linspace(1.2, 3.2, 41)
T_GRID = np.linspace(0.25, 3.0, 45)
PRIOR_M, PRIOR_M_SD = 2.0, 0.6
PRIOR_T, PRIOR_T_SD = 1.2, 0.6
KAPPA = 0.5           # weight on other zones' CLPU information (partial personalisation)
ROUNDS = 5            # aggregation rounds per 15-min step (5 x 128 s = 640 s of the 900-s step); v1.0: 3
ETA_LAMBDA = 1.0
MAX_LOG_STEP = 0.25   # trust region on the log-price update per round
DF_TARGET_HZ = 0.10   # peak frequency excursion targeted by the pilot amplitude control
AMP_MAX_MW = 0.015    # pilot amplitude cap per code and zone (inverter head-room)
DEFICIT_MARGIN = 0.0  # shed energised blocks only when the perceived gap is below -margin
AGG_BETA = 0.0        # smoothing of decoded aggregates across rounds (0 = none)
RHO_H = 8.0           # hours of service lost that a re-interruption is worth (hysteresis)
PRICE_AVG = True      # ergodic (geometric-mean) averaging of the price over the R rounds of a step; v1.0: False
TD_OUTAGE = 3.0       # h, saturation constant of CLPU magnitude vs outage duration
D0_OUTAGE = 2.0       # h, outage duration before the restoration window starts

LOAD_BLOCKS = np.array([b for b in range(NET["n"]) if NET["p_nom"][b] > 0])
B_ZONE = NET["zone_of"][LOAD_BLOCKS]
P_B = NET["p_nom"][LOAD_BLOCKS]
Q_B = NET["q_nom"][LOAD_BLOCKS]
FIXED_CRITICAL = {3, 6, 29}          # hospital (Z1), emergency shelter / EOC (Z2), water pumping (Z4)
FIXED_ESSENTIAL = {23, 31}           # transit hub (Z1), waste-water (Z4)


def hour(k):
    return (H0 + k * DT) % 24


def gfun(h):
    h = np.asarray(h) % 24
    i = np.floor(h).astype(int); f = h - i
    return G_HOURLY[i] * (1 - f) + G_HOURLY[(i + 1) % 24] * f


def clearsky(h):
    h = np.asarray(h) % 24
    return np.clip(np.sin(np.pi * (h - 6) / 12), 0, None) ** 1.2 * ((h > 6) & (h < 18))


GK = gfun(hour(np.arange(STEPS)))
CSK = clearsky(hour(np.arange(STEPS)))


# ------------------------------------------------------------------ scenario
def make_scenario(seed):
    rng = np.random.default_rng(10_000 + seed)
    nb = len(LOAD_BLOCKS)
    cls = []
    for b, z in zip(LOAD_BLOCKS, B_ZONE):
        if b in FIXED_CRITICAL:
            cls.append("critical")
        elif b in FIXED_ESSENTIAL:
            cls.append("essential")
        else:
            pe = 0.10 if z == 2 else 0.30
            cls.append("essential" if rng.random() < pe else "normal")
    cw = np.array([CLASS_W[c] for c in cls])
    omega = cw * (1 + 0.2 * rng.random(nb))                 # within-class social priority index
    m_true = rng.uniform(1.5, 2.8); t_true = rng.uniform(0.5, 2.5)
    m_z = m_true * (1 + rng.normal(0, 0.05, N_ZONES)); t_z = t_true * (1 + rng.normal(0, 0.10, N_ZONES))
    day = rng.choice([0.9, 0.6, 0.3], p=[0.4, 0.4, 0.2])    # clear / partly cloudy / overcast
    cloud_common = np.clip(day + 0.15 * np.cumsum(rng.normal(0, 0.15, STEPS)) * 0.3, 0.05, 1.0)
    cloud = np.clip(cloud_common[None, :] + rng.normal(0, 0.08, (N_ZONES, STEPS)), 0.0, 1.0)
    pv = NET["pv_rated"][:, None] * CSK[None, :] * cloud                   # MW, actual
    fc_err = 1 + rng.normal(0, 0.15, N_ZONES)
    pv_fc = NET["pv_rated"][:, None] * CSK[None, :] * np.clip(day * fc_err, 0.05, 1.0)[:, None]
    load_noise = rng.normal(0, 0.03, (STEPS, nb))
    meas_noise = rng.normal(0, 0.02, (STEPS, N_ZONES))
    soe0 = rng.uniform(0.7, 0.95, N_ZONES)
    return dict(cls=np.array(cls), cw=cw, omega=omega, m_z=m_z, t_z=t_z, m_true=m_true, t_true=t_true,
                day=day, pv=pv, pv_fc=pv_fc, load_noise=load_noise, meas_noise=meas_noise, soe0=soe0,
                seed=seed)


# ------------------------------------------------------------------ CLPU learner
class CLPULearner:
    def __init__(self):
        self.ll = np.zeros((len(M_GRID), len(T_GRID)))
        self.n_obs = 0

    def update(self, p, g, c, age, meas):
        """p, c, age: arrays of the zone's energised blocks; meas: measured zone demand."""
        if len(p) == 0:
            return
        base = (p * g).sum()
        S = (p * g * c)[None, :] * np.exp(-age[None, :] / T_GRID[:, None])   # T x B
        S = S.sum(1)
        pred = base + (M_GRID[:, None] - 1) * S[None, :]
        sig = 0.02 * meas + 1e-4
        self.ll += -(meas - pred) ** 2 / (2 * sig ** 2)
        self.n_obs += 1

    def likelihood_summary(self):
        """Gaussian summary (mean, precision) of the likelihood alone (flat prior on grid)."""
        if self.n_obs == 0 or np.ptp(self.ll) < 1e-6:
            return np.array([PRIOR_M, PRIOR_T]), np.zeros(2)
        L = np.exp(self.ll - self.ll.max()); L /= L.sum()
        pm = L.sum(1); pt = L.sum(0)
        mu = np.array([(pm * M_GRID).sum(), (pt * T_GRID).sum()])
        var = np.array([(pm * (M_GRID - mu[0]) ** 2).sum(), (pt * (T_GRID - mu[1]) ** 2).sum()])
        var = np.maximum(var, np.array([(M_GRID[1] - M_GRID[0]) ** 2, (T_GRID[1] - T_GRID[0]) ** 2]) / 12)
        return mu, 1 / var


PRIOR_MU = np.array([PRIOR_M, PRIOR_T])
PRIOR_PREC = np.array([1 / PRIOR_M_SD ** 2, 1 / PRIOR_T_SD ** 2])


def personalised_estimate(mu_k, lam_k, mu_pop=None, lam_others=None):
    num = PRIOR_PREC * PRIOR_MU + lam_k * mu_k
    den = PRIOR_PREC + lam_k
    if mu_pop is not None:
        lo = np.maximum(lam_others, 0) * KAPPA
        num = num + lo * mu_pop; den = den + lo
    est = num / den
    return np.array([np.clip(est[0], 1.0, 3.5), np.clip(est[1], 0.2, 3.5)])


# ------------------------------------------------------------------ zone planner
def zone_plan(z, k, lam, theta, on, age, off_dur, pv_fc_z, e_avail, e_cap, omega, deficit=True):
    """Plan of zone z at step k for energy price lam (value units per MWh).
    Returns desired on-mask for the zone's blocks, surplus at checkpoints, new pick-ups."""
    idx = np.where(B_ZONE == z)[0]
    m_hat, t_hat = theta
    rem = STEPS - k
    j = np.arange(rem)
    g = GK[k:]
    c = 1 - np.exp(-off_dur[idx] / TD_OUTAGE)
    a = np.where(on[idx][:, None], age[idx][:, None] + j[None, :] * DT + DT / 2, j[None, :] * DT + DT / 2)
    meff = np.where(on[idx], np.nan, 1 + (m_hat - 1) * c)
    meff_on = ON_MEFF[idx]
    meff = np.where(on[idx], 1 + (m_hat - 1) * meff_on, meff)
    prof = P_B[idx][:, None] * g[None, :] * (1 + (meff[:, None] - 1) * np.exp(-a / t_hat))   # MW per step
    E = prof.sum(1) * DT
    V = omega[idx] * (P_B[idx][:, None] * g[None, :]).sum(1) * DT
    rho = omega[idx] * P_B[idx] * RHO_H
    # no-regret rule: an energised block is only shed when the (perceived) budget is in deficit
    keep = (V + rho >= lam * E) | (not deficit)
    want = np.where(on[idx], keep, V >= lam * E)
    load_traj = (prof * want[:, None]).sum(0)
    s = e_avail; traj = np.empty(rem)
    for i in range(rem):
        d = pv_fc_z[k + i] - load_traj[i]
        s = min(s + d * DT * (ETA if d > 0 else 1 / ETA), e_cap)
        traj[i] = s
    cps = np.array([traj[min(int(h / DT), rem) - 1] for h in CHECKPOINTS_H])
    new = idx[want & ~on[idx]]
    new = new[np.argsort(-omega[new])]
    req_each = P_B[new] * GK[k] * (1 + (m_hat - 1) * (1 - np.exp(-off_dur[new] / TD_OUTAGE)))
    return idx[want], cps, new, req_each


ON_MEFF = np.zeros(len(LOAD_BLOCKS))      # set per run: CLPU magnitude factor c_b fixed at energisation


# ------------------------------------------------------------------ simulation
def run(scn, method, p_link=1.0, dp_sigma=0.0, otg_amp=0.006, otg_len=128, seed_offset=0, pf_check=True,
        load_sigma_frac=0.005, fuse_clpu=True, code_order="drift", pv_ramp=0.0, overrides=None):
    """pv_ramp: multiplier on the PV change that occurs during each RCD round (0 = v1.0 channel).
    overrides: dict of module parameters for sensitivity studies (ROUNDS, ETA_LAMBDA, RHO_H, KAPPA)."""
    global ON_MEFF, ROUNDS, ETA_LAMBDA, RHO_H, KAPPA, PRICE_AVG
    saved = dict(ROUNDS=ROUNDS, ETA_LAMBDA=ETA_LAMBDA, RHO_H=RHO_H, KAPPA=KAPPA, PRICE_AVG=PRICE_AVG)
    for kk, vv in (overrides or {}).items():
        globals()[kk] = vv
    try:
        return _run(scn, method, p_link, dp_sigma, otg_amp, otg_len, seed_offset, pf_check, load_sigma_frac,
                    fuse_clpu, code_order, pv_ramp)
    finally:
        globals().update(saved)


def _run(scn, method, p_link, dp_sigma, otg_amp, otg_len, seed_offset, pf_check, load_sigma_frac, fuse_clpu,
         code_order, pv_ramp):
    global ON_MEFF
    rng_m = np.random.default_rng(scn["seed"] * 1000 + 17 + seed_offset)   # method-specific randomness
    rng_link = np.random.default_rng(scn["seed"] * 7 + 3)                 # same link process across p
    nb = len(LOAD_BLOCKS)
    on = np.zeros(nb, bool); age = np.zeros(nb); off_dur = np.full(nb, D0_OUTAGE)
    ON_MEFF = np.zeros(nb)
    meff_true = np.zeros(nb)
    soe = scn["soe0"].copy()
    E_cap = NET["e_rated"] * (1 - SOE_MIN)
    learners = [CLPULearner() for _ in range(N_ZONES)]
    lam = np.ones(N_ZONES)                                    # each zone keeps its own price copy
    deficit = np.ones(N_ZONES, bool)                          # perceived energy deficit (from last round)
    coordinated = method in ("full_info", "otg", "otg_dp") or method.startswith("telecom")
    soc_droop = method != "local_rating"
    quantities = ([("cp%d" % i, 3.0, False) for i in range(len(CHECKPOINTS_H))] +
                  [("head", 1.5, False), ("req", 1.5, False),
                   ("clpu_m", 1.0, True), ("clpu_t", 1.5, True), ("prec_m", 1.0, False), ("prec_t", 1.0, False)])
    ch = RCDChannel(quantities, length=otg_len, amplitude_mw=otg_amp, code_order=code_order)
    amp = otg_amp
    agg_ema = [None] * N_ZONES
    # telecom link Markov chains
    q_du = 1 / 8.0
    q_ud = q_du * (1 - p_link) / p_link if p_link > 0 else 1.0
    link = rng_link.random(N_ZONES) < p_link
    last_load = np.zeros(N_ZONES); last_pv = np.zeros(N_ZONES)
    log = dict(pwes=0.0, crit_served=0.0, crit_total=0.0, energy=0.0, reint_planned=0, reint_ufls=0,
               ufls_events=0, vmin=[], vmax=[], df_pilot_mhz=0.0, pf_fail=0, lam=[], soe=[], served_mw=[],
               clpu_err=[], agg_err=[])
    for k in range(STEPS):
        if method.startswith("telecom"):
            u = rng_link.random(N_ZONES)
            link = np.where(link, u >= q_ud, u < q_du)
        e_avail = np.maximum(soe - SOE_MIN, 0) * NET["e_rated"]
        # ---- CLPU estimates
        summaries = [learners[z].likelihood_summary() for z in range(N_ZONES)]
        theta_local = [personalised_estimate(*summaries[z]) for z in range(N_ZONES)]
        theta = list(theta_local)
        if method == "full_info":
            theta = [np.array([scn["m_z"][z], scn["t_z"][z]]) for z in range(N_ZONES)]
        pv_fc = scn["pv"] if method == "full_info" else scn["pv_fc"]
        headroom = (NET["p_rated"] * (e_avail > 1e-3) + last_pv - last_load - 0.05 * NET["p_rated"])
        if k == 0:
            headroom = NET["p_rated"] * 0.6 - 0.05 * NET["p_rated"]
        # ---- price negotiation
        if method == "full_info":
            lo, hi = -4.0, 5.0
            for _ in range(16):
                mid = 0.5 * (lo + hi)
                S = sum(zone_plan(z, k, np.exp(mid), theta[z], on, age, off_dur, pv_fc[z], e_avail[z], E_cap[z],
                                  scn["omega"])[1] for z in range(N_ZONES))
                if S.min() >= 0.05 * E_cap.sum():
                    hi = mid
                else:
                    lo = mid
            lam[:] = np.exp(hi)
            S_keep = sum(zone_plan(z, k, lam[z], theta[z], on, age, off_dur, pv_fc[z], e_avail[z], E_cap[z],
                                   scn["omega"], False)[1] for z in range(N_ZONES))
            dfc = S_keep.min() < 0.05 * E_cap.sum()
            plans = [zone_plan(z, k, lam[z], theta[z], on, age, off_dur, pv_fc[z], e_avail[z], E_cap[z],
                               scn["omega"], dfc) for z in range(N_ZONES)]
            H = headroom.sum(); R = sum(p[3].sum() for p in plans)
            phi = np.full(N_ZONES, np.clip(H / R, 0, 1) if R > 0 else 1.0)
        else:
            loglam_hist = []
            for r in range(ROUNDS):
                plans = [zone_plan(z, k, lam[z], theta[z], on, age, off_dur, pv_fc[z], e_avail[z], E_cap[z],
                                   scn["omega"], deficit[z]) for z in range(N_ZONES)]
                cps = np.array([p[1] for p in plans])
                reqs = np.array([p[3].sum() for p in plans])
                mus = np.array([s[0] for s in summaries]); precs = np.array([s[1] for s in summaries])
                wts = precs / (precs + PRIOR_PREC)
                vals = {("cp%d" % i): cps[:, i] for i in range(len(CHECKPOINTS_H))}
                vals.update(head=headroom, req=reqs, clpu_m=mus[:, 0] - PRIOR_M, clpu_t=mus[:, 1] - PRIOR_T,
                            prec_m=np.minimum(precs[:, 0] / 400, 1), prec_t=np.minimum(precs[:, 1] / 400, 1))
                truth = {kq: (np.mean(v) if kq not in ("clpu_m", "clpu_t") else
                              (wts[:, 0 if kq == "clpu_m" else 1] * v).sum() / max(wts[:, 0 if kq == "clpu_m" else 1].sum(), 1e-12))
                         for kq, v in vals.items()}
                agg = [None] * N_ZONES
                if method in ("otg", "otg_dp"):
                    Z = ch.contributions(vals, dict(clpu_m=wts[:, 0], clpu_t=wts[:, 1]),
                                         dict(clpu_m=1.0, clpu_t=1.0), dp_sigma=dp_sigma, rng=rng_m)
                    ch.A = amp
                    P = ch.pilot_powers(Z)
                    Dk = droop_gains(NET["p_rated"], soe if soc_droop else None)
                    # PV change during this round (128 s of the 15-min step), linear + quadratic part
                    kn = min(k + 1, STEPS - 1)
                    dpv = (scn["pv"][:, kn] - scn["pv"][:, k]).sum() * otg_len / (DT * 3600)
                    meas = linear_channel(P, Dk.sum(), rng_m, load_sigma_mw=load_sigma_frac * max(last_load.sum(), 0.3),
                                          n_listeners=N_ZONES, ramp_mw=-pv_ramp * dpv,
                                          curv_mw=pv_ramp * 0.25 * abs(dpv))
                    # self-normalising amplitude: every zone sees the same frequency peak, so all
                    # zones apply the same quantised gain (ratio decoding is invariant to it)
                    pk = np.abs(meas[0]).max() * F0_HZ
                    gain = 2 ** (np.round(4 * np.log2(np.clip(DF_TARGET_HZ / pk, 0.5, 2))) / 4)
                    amp = float(np.clip(amp * gain, 0.001, AMP_MAX_MW))
                    log["df_pilot_mhz"] = max(log["df_pilot_mhz"], float(np.abs(P.sum(0)).max() / Dk.sum() * F0_HZ * 1e3))
                    for z in range(N_ZONES):
                        dec = ch.decode(meas[z])[0]
                        # exponential smoothing of decoded aggregates across rounds (noise filter)
                        if agg_ema[z] is None:
                            agg_ema[z] = dict(dec)
                        else:
                            for kq, v in dec.items():
                                if np.isfinite(v):
                                    agg_ema[z][kq] = AGG_BETA * agg_ema[z][kq] + (1 - AGG_BETA) * v
                        agg[z] = agg_ema[z]
                    log["agg_err"].append(np.mean([abs(agg[0]["cp%d" % i] - truth["cp%d" % i]) for i in range(len(CHECKPOINTS_H))]))
                elif method.startswith("telecom"):
                    up = np.where(link)[0]
                    if len(up) > 0:
                        a_up = {}
                        for kq, v in vals.items():
                            if kq in ("clpu_m", "clpu_t"):
                                w = wts[up, 0 if kq == "clpu_m" else 1]
                                a_up[kq] = (w * v[up]).sum() / w.sum() if w.sum() > 1e-12 else 0.0
                            else:
                                a_up[kq] = v[up].mean()        # coordinator extrapolates missing zones
                        for z in up:
                            agg[z] = a_up
                # ---- each zone updates its own price copy from what it received
                for z in range(N_ZONES):
                    if agg[z] is not None:
                        smin = min(agg[z]["cp%d" % i] for i in range(len(CHECKPOINTS_H))) * N_ZONES
                        gap = (smin - 0.05 * E_cap.sum()) / E_cap.sum()
                    else:
                        gap = (cps[z].min() - 0.05 * E_cap[z]) / E_cap[z]
                    lam[z] = float(np.clip(lam[z] * np.exp(np.clip(-ETA_LAMBDA * gap, -MAX_LOG_STEP, MAX_LOG_STEP)),
                                           0.02, 60.0))
                    deficit[z] = gap < -DEFICIT_MARGIN
                loglam_hist.append(np.log(lam))
                # ---- federated CLPU fusion (personalised)
                for z in range(N_ZONES):
                    if agg[z] is not None and coordinated and fuse_clpu:
                        mu_pop = np.array([agg[z]["clpu_m"] + PRIOR_M, agg[z]["clpu_t"] + PRIOR_T])
                        lam_all = np.array([agg[z]["prec_m"], agg[z]["prec_t"]]) * 400 * N_ZONES
                        if np.all(np.isfinite(mu_pop)):
                            theta[z] = personalised_estimate(summaries[z][0], summaries[z][1], mu_pop,
                                                             lam_all - summaries[z][1])
                    else:
                        theta[z] = theta_local[z]
            if PRICE_AVG:    # each zone averages its OWN price copies over the rounds (no communication)
                lam = np.exp(np.mean(loglam_hist, axis=0))
            plans = [zone_plan(z, k, lam[z], theta[z], on, age, off_dur, pv_fc[z], e_avail[z], E_cap[z],
                               scn["omega"], deficit[z]) for z in range(N_ZONES)]
            phi = np.zeros(N_ZONES)
            for z in range(N_ZONES):
                if agg[z] is not None:
                    H = agg[z]["head"] * N_ZONES; R = agg[z]["req"] * N_ZONES
                else:
                    H = headroom[z]; R = plans[z][3].sum()
                phi[z] = np.clip(H / R, 0, 1) if R > 1e-9 else 1.0
        # ---- apply decisions (keep / shed planned, pick up within the power allocation)
        new_on = np.zeros(nb, bool)
        for z in range(N_ZONES):
            keep, _, new, req_each = plans[z]
            keep_mask = np.zeros(nb, bool); keep_mask[keep] = True
            idx = np.where(B_ZONE == z)[0]
            shed = idx[on[idx] & ~keep_mask[idx]]
            log["reint_planned"] += len(shed)
            new_on[idx] = on[idx] & keep_mask[idx]
            budget = phi[z] * req_each.sum(); used = 0.0
            for b, rq in zip(new, req_each):
                if used + rq <= budget + 1e-9:
                    new_on[b] = True; used += rq
                    c = 1 - np.exp(-off_dur[b] / TD_OUTAGE)
                    ON_MEFF[b] = c
                    meff_true[b] = 1 + (scn["m_z"][z] - 1) * c
                    age[b] = 0.0
        on = new_on
        # ---- physics: actual demand, droop sharing, UFLS
        a_mid = age + DT / 2
        tz = scn["t_z"][B_ZONE]
        dem = P_B * GK[k] * (1 + (meff_true - 1) * np.exp(-a_mid / tz)) * (1 + scn["load_noise"][k]) * on
        pv_now = scn["pv"][:, k]
        while True:
            net = dem.sum() - pv_now.sum()
            pmax = np.minimum(NET["p_rated"], np.maximum(soe - SOE_MIN, 0) * NET["e_rated"] * ETA / DT)
            if net <= pmax.sum() + 1e-9 or not on.any():
                break
            cand = np.where(on)[0]
            b = cand[np.argmin(scn["omega"][cand])]          # UFLS stages trip lowest priority first
            on[b] = False; dem[b] = 0.0
            log["reint_ufls"] += 1
            log["ufls_events"] += 1
        net = dem.sum() - pv_now.sum()
        P_out = np.zeros(N_ZONES)
        if net > 0:
            share = NET["p_rated"] * (np.clip(soe, 0.02, 1) if soc_droop else 1.0)
            rem = net; active = pmax > 1e-9
            for _ in range(N_ZONES):
                w = share * active
                if w.sum() <= 0:
                    break
                alloc = rem * w / w.sum()
                over = alloc > pmax - P_out
                P_out += np.minimum(alloc, pmax - P_out)
                rem = net - P_out.sum()
                active = active & ~over
                if rem <= 1e-9:
                    break
            soe -= P_out * DT / ETA / NET["e_rated"]
        else:
            room = np.minimum(NET["p_rated"], (1 - soe) * NET["e_rated"] / (ETA * DT))
            w = NET["p_rated"] * (1 - soe)
            ch_p = np.minimum(-net * w / max(w.sum(), 1e-9), room)
            P_out = -ch_p
            soe += ch_p * DT * ETA / NET["e_rated"]
        soe = np.clip(soe, 0, 1)
        if pf_check and on.any():
            pl = np.zeros(NET["n"]); ql = np.zeros(NET["n"])
            pl[LOAD_BLOCKS] = dem; ql[LOAD_BLOCKS] = dem * Q_B / P_B
            pv_bus = np.zeros(NET["n"]); pv_bus[NET["gfm_bus"]] = pv_now
            Dk = droop_gains(NET["p_rated"], soe if soc_droop else None)
            r = droop_powerflow(NET["Y"], NET["gfm_bus"], P_out + 0.01 * Dk / Dk.sum(), Dk, NQ * NET["p_rated"],
                                pl, ql, pv_bus)
            if r["converged"]:
                log["vmin"].append(float(r["Vm"].min())); log["vmax"].append(float(r["Vm"].max()))
            else:
                log["pf_fail"] += 1
        # ---- book-keeping and learning
        nominal = P_B * GK[k] * DT
        log["pwes"] += float((scn["cw"] * nominal * on).sum())
        crit = scn["cls"] == "critical"
        log["crit_served"] += float((nominal * on * crit).sum()); log["crit_total"] += float((nominal * crit).sum())
        log["energy"] += float(dem.sum() * DT)
        log["lam"].append(float(np.median(lam))); log["soe"].append(soe.copy().tolist())
        log["served_mw"].append(float(dem.sum()))
        for z in range(N_ZONES):
            idx = np.where((B_ZONE == z) & on)[0]
            zd = dem[idx].sum()
            meas = zd * (1 + scn["meas_noise"][k, z])
            learners[z].update(P_B[idx], GK[k], ON_MEFF[idx], a_mid[idx], meas)
            last_load[z] = zd * GK[min(k + 1, STEPS - 1)] / GK[k]
        last_pv = pv_now.copy()
        log["clpu_err"].append(float(np.mean([abs(theta[z][0] - scn["m_z"][z]) for z in range(N_ZONES)])))
        age = np.where(on, age + DT, 0.0)
        off_dur = np.where(on, 0.0, off_dur + DT)
    log["crit_frac"] = log["crit_served"] / log["crit_total"]
    log["vmin"] = min(log["vmin"]) if log["vmin"] else np.nan
    log["vmax"] = max(log["vmax"]) if log["vmax"] else np.nan
    log["reint_total"] = log["reint_planned"] + log["reint_ufls"]
    log["agg_err"] = float(np.mean(log["agg_err"])) if log["agg_err"] else 0.0
    log["min_soe"] = float(np.min(log["soe"]))
    return log
