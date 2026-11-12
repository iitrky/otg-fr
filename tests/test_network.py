"""Islanded droop AC power flow: convergence, power balance, droop law."""
import numpy as np
from otgfr.network import build_network, droop_powerflow, droop_gains, NQ

NET = build_network()


def _solve(level=0.6, p_set=None, soe=None):
    D = droop_gains(NET["p_rated"], soe)
    pl, ql = NET["p_nom"] * level, NET["q_nom"] * level
    if p_set is None:
        p_set = np.zeros(len(D))
    return droop_powerflow(NET["Y"], NET["gfm_bus"], p_set, D, NQ * NET["p_rated"], pl, ql,
                           np.zeros(NET["n"])), D, pl


def test_converges_and_balances_power():
    r, D, pl = _solve()
    assert r["converged"]
    assert abs(r["P_gfm"].sum() - pl.sum() - r["losses"]) < 1e-8


def test_droop_sharing_is_proportional_to_gain():
    r, D, _ = _solve()
    share = r["P_gfm"] / r["P_gfm"].sum()
    assert np.allclose(share, D / D.sum(), atol=1e-9)


def test_frequency_equals_imbalance_over_stiffness():
    r, D, pl = _solve(p_set=np.full(4, 0.3))
    pred = (1.2 - pl.sum() - r["losses"]) / D.sum()
    assert abs(r["dw"] - pred) < 1e-10
