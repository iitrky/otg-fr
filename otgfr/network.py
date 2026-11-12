"""
Islanded IEEE 33-bus test feeder with grid-forming (GFM) inverters and an
AC power-flow solver for droop control (islanded "droop power flow").

The substation (bus 1, index 0) is assumed lost (upstream black-out). The feeder
operates as one island. Grid-forming battery inverters in four zones hold voltage
and frequency through P-f and Q-V droop. Tie lines 18-33 and 25-29 (1-indexed)
are closed during restoration to mesh the island. All quantities are per unit on
S_base = 1 MVA, V_base = 12.66 kV, f_base = 60 Hz.
"""
import numpy as np
import pandapower.networks as pn

S_BASE_MVA = 1.0
V_BASE_KV = 12.66
F0_HZ = 60.0
Z_BASE = V_BASE_KV ** 2 / S_BASE_MVA
TIES_CLOSED = [(17, 32), (24, 28)]          # 0-indexed bus pairs

# ---------------------------------------------------------------- zones and DER
ZONES = {
    # name: buses (0-indexed), GFM bus, BESS power MW, BESS energy MWh, PV MW
    "Z1-urban core": dict(buses=[0, 1, 2, 3, 4, 18, 19, 20, 21, 22, 23, 24], gfm=2,
                          p_mw=0.60, e_mwh=2.0, pv_mw=0.30),
    "Z2-civic":      dict(buses=[5, 6, 7, 8, 9, 10, 11, 12], gfm=7,
                          p_mw=0.80, e_mwh=2.5, pv_mw=0.40),
    "Z3-solar park": dict(buses=[13, 14, 15, 16, 17], gfm=15,
                          p_mw=1.60, e_mwh=7.0, pv_mw=2.00),
    "Z4-utilities":  dict(buses=[25, 26, 27, 28, 29, 30, 31, 32], gfm=29,
                          p_mw=0.80, e_mwh=2.5, pv_mw=0.50),
}
ZONE_NAMES = list(ZONES)
N_ZONES = len(ZONES)
MP = 0.02      # P-f droop: 2 % frequency drop at rated power
NQ = 0.05      # Q-V droop: 5 % voltage drop at rated (=P rating) reactive power
V0 = 1.03      # no-load GFM voltage set-point


def build_network():
    net = pn.case33bw()
    n = len(net.bus)
    Y = np.zeros((n, n), dtype=complex)
    lines = net.line[net.line.in_service].copy()
    rows = [(int(r.from_bus), int(r.to_bus), r.r_ohm_per_km * r.length_km, r.x_ohm_per_km * r.length_km)
            for r in lines.itertuples()]
    for (f, t) in TIES_CLOSED:
        tie = net.line[(net.line.from_bus == f) & (net.line.to_bus == t)].iloc[0]
        rows.append((f, t, tie.r_ohm_per_km * tie.length_km, tie.x_ohm_per_km * tie.length_km))
    for f, t, r, x in rows:
        y = 1.0 / ((r + 1j * x) / Z_BASE)
        Y[f, f] += y; Y[t, t] += y; Y[f, t] -= y; Y[t, f] -= y
    p_load = np.zeros(n); q_load = np.zeros(n)
    for r in net.load.itertuples():
        p_load[int(r.bus)] += r.p_mw / S_BASE_MVA
        q_load[int(r.bus)] += r.q_mvar / S_BASE_MVA
    zone_of = np.full(n, -1)
    for k, z in enumerate(ZONES.values()):
        zone_of[z["buses"]] = k
    assert (zone_of >= 0).all()
    return dict(Y=Y, n=n, p_nom=p_load, q_nom=q_load, zone_of=zone_of,
                gfm_bus=np.array([z["gfm"] for z in ZONES.values()]),
                p_rated=np.array([z["p_mw"] for z in ZONES.values()]),
                e_rated=np.array([z["e_mwh"] for z in ZONES.values()]),
                pv_rated=np.array([z["pv_mw"] for z in ZONES.values()]))


def droop_powerflow(Y, gfm_bus, p_set, D, nq_pu, p_load, q_load, p_pv, v0=V0, x0=None,
                    tol=1e-10, max_it=30):
    """Islanded AC power flow with P-f / Q-V droop at the GFM buses.

    Unknowns: voltage angles (all buses except the first GFM bus), magnitudes (all), and
    the common steady-state frequency deviation dw (pu). Loads are constant power; PV is a
    constant-power (unity power factor) injection.
    Returns dict with Vm, Va, dw, P_gfm (output of each GFM, pu), losses (pu), converged.
    """
    n = Y.shape[0]
    ref = gfm_bus[0]
    ang_idx = np.array([i for i in range(n) if i != ref])
    G = len(gfm_bus)
    Cg = np.zeros((n, G)); Cg[gfm_bus, np.arange(G)] = 1.0
    if x0 is None:
        Va = np.zeros(n); Vm = np.full(n, v0); dw = 0.0
    else:
        Va, Vm, dw = x0
        Va = Va.copy(); Vm = Vm.copy()
    for it in range(max_it):
        V = Vm * np.exp(1j * Va)
        I = Y @ V
        S = V * np.conj(I)
        Pg = p_set - D * dw
        Qg = (v0 - Vm[gfm_bus]) / nq_pu
        P_spec = Cg @ Pg - p_load + p_pv
        Q_spec = Cg @ Qg - q_load
        F = np.concatenate([S.real - P_spec, S.imag - Q_spec])
        if np.max(np.abs(F)) < tol:
            break
        dS_dVa = 1j * np.diag(V) @ np.conj(np.diag(I) - Y @ np.diag(V))
        Vn = V / Vm
        dS_dVm = np.diag(V) @ np.conj(Y @ np.diag(Vn)) + np.conj(np.diag(I)) @ np.diag(Vn)
        J = np.zeros((2 * n, 2 * n))
        J[:n, :n - 1] = dS_dVa.real[:, ang_idx]
        J[n:, :n - 1] = dS_dVa.imag[:, ang_idx]
        J[:n, n - 1:2 * n - 1] = dS_dVm.real
        J[n:, n - 1:2 * n - 1] = dS_dVm.imag
        J[n + gfm_bus, n - 1 + gfm_bus] += 1.0 / nq_pu          # dQspec/dVm
        J[:n, 2 * n - 1] = Cg @ D                                # dPspec/ddw (sign: F = S - Pspec)
        dx = np.linalg.solve(J, -F)
        Va[ang_idx] += dx[:n - 1]
        Vm += dx[n - 1:2 * n - 1]
        dw += dx[2 * n - 1]
    V = Vm * np.exp(1j * Va)
    S = V * np.conj(Y @ V)
    losses = S.real.sum()
    conv = bool(np.max(np.abs(F)) < 1e-8)
    return dict(Vm=Vm, Va=Va, dw=dw, P_gfm=p_set - D * dw, losses=losses, converged=conv,
                x=(Va, Vm, dw))


def droop_gains(p_rated, soe=None, soc_exponent=1.0):
    """P-f droop gains D_k (pu power per pu frequency). SoC-adaptive if soe given."""
    D = p_rated / MP
    if soe is not None:
        D = D * np.clip(soe, 0.02, 1.0) ** soc_exponent
    return D


if __name__ == "__main__":
    import time
    net = build_network()
    D = droop_gains(net["p_rated"])
    nq = NQ * net["p_rated"]
    p_set = net["p_nom"].sum() * net["p_rated"] / net["p_rated"].sum() * 0.0
    t = time.time()
    r = droop_powerflow(net["Y"], net["gfm_bus"], p_set, D, nq, net["p_nom"] * 0.7, net["q_nom"] * 0.7,
                        np.zeros(net["n"]))
    print("converged", r["converged"], "df Hz", r["dw"] * F0_HZ, "Vmin", r["Vm"].min(), "Vmax", r["Vm"].max(),
          "loss MW", r["losses"], "P_gfm", r["P_gfm"], "time", time.time() - t)
