"""Algorithm 2: orthogonality, exact decoding, invariance to unknown stiffness and amplitude."""
import numpy as np
from otgfr.rcd import walsh_codes, RCDChannel, zcdp_epsilon


def test_codes_zero_mean_and_orthogonal():
    C = walsh_codes(20, 64)
    assert np.allclose(C.sum(1), 0)
    assert np.allclose(C @ C.T, 64 * np.eye(20))


def _channel():
    return RCDChannel([("m", 1.0, False), ("w", 1.0, True)], length=64, amplitude_mw=0.01)


def test_noise_free_decoding_is_exact_and_stiffness_invariant():
    rng = np.random.default_rng(0)
    ch = _channel()
    x, y, w = rng.uniform(-.9, .9, 6), rng.uniform(-.9, .9, 6), rng.uniform(.05, 1, 6)
    Z = ch.contributions(dict(m=x, w=y), dict(w=w), dict(w=1.0))
    P = ch.pilot_powers(Z)
    for D_total in [5.0, 50.0, 500.0]:              # unknown to the zones
        for offset in [0.0, 0.3]:                   # constant load imbalance
            est, _ = ch.decode(P.sum(0) / D_total + offset)
            assert abs(est["m"] - x.mean()) < 1e-12
            assert abs(est["w"] - (w * y).sum() / w.sum()) < 1e-12


def test_common_amplitude_change_cancels():
    rng = np.random.default_rng(1)
    ch = _channel()
    x = rng.uniform(-.9, .9, 4)
    Z = ch.contributions(dict(m=x, w=x), dict(w=np.ones(4)), dict(w=1.0))
    ch.A = 0.003
    est, _ = ch.decode(ch.pilot_powers(Z).sum(0) / 40.0)
    assert abs(est["m"] - x.mean()) < 1e-12


def test_linear_drift_rejected_by_high_sequency_codes():
    ch = _channel()
    drift = np.linspace(-1, 1, 64)
    y = ch.C @ drift / 64
    assert np.max(np.abs(y)) < 0.02


def test_dp_epsilon_decreases_with_noise():
    assert zcdp_epsilon(1, 1.0, 10) < zcdp_epsilon(1, 0.5, 10)


def test_drift_order_codes_reject_polynomial_drift_exactly():
    """Proposition 2: Sylvester row i is orthogonal to t^j for j < popcount(i)."""
    from otgfr.rcd import code_drift_order
    C = walsh_codes(13, 128, order="drift")
    assert code_drift_order(C) >= 5
    assert code_drift_order(walsh_codes(13, 128, order="sequency")) == 1
    rng = np.random.default_rng(3)
    ch = RCDChannel([("m", 1.0, False), ("w", 1.0, True)], length=128, amplitude_mw=0.006)
    x, y, w = rng.uniform(-.9, .9, 4), rng.uniform(-.9, .9, 4), rng.uniform(.05, 1, 4)
    P = ch.pilot_powers(ch.contributions(dict(m=x, w=y), dict(w=w), dict(w=1.0)))
    t = np.linspace(-1, 1, 128)
    drift = 0.5 * t + 0.3 * t ** 2 - 0.2 * t ** 3 + 0.1 * t ** 4      # 0.5 MW ramp >> 6 kW pilots
    est, _ = ch.decode((P.sum(0) - drift) / 80.0)
    assert abs(est["m"] - x.mean()) < 1e-9
    assert abs(est["w"] - (w * y).sum() / w.sum()) < 1e-9
