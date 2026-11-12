"""Algorithm 1: end-to-end smoke tests on one scenario (no AC check, for speed)."""
import numpy as np
from otgfr.restoration import make_scenario, run


def test_methods_run_and_order_is_sensible():
    scn = make_scenario(0)
    full = run(scn, "full_info", pf_check=False)
    loc = run(scn, "local_soc", pf_check=False)
    otg = run(scn, "otg", pf_check=False)
    assert full["crit_frac"] > 0.99
    assert otg["pwes"] > loc["pwes"]
    assert otg["crit_frac"] >= loc["crit_frac"]
    assert otg["df_pilot_mhz"] < 250


def test_determinism():
    scn = make_scenario(3)
    a = run(scn, "otg", pf_check=False)
    b = run(scn, "otg", pf_check=False)
    assert a["pwes"] == b["pwes"] and a["reint_total"] == b["reint_total"]


def test_telecom_full_availability_matches_full_info_closely():
    scn = make_scenario(1)
    full = run(scn, "full_info", pf_check=False)
    tel = run(scn, "telecom", p_link=1.0, pf_check=False)
    assert tel["pwes"] / full["pwes"] > 0.95
