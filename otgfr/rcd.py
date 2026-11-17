"""
Algorithm 2 - Ratio-Coded Droop aggregation (RCD).

Every grid-forming zone k superimposes a small spread-spectrum power pilot on its droop
set-point:     p_k(t) = A * sum_m z_km * c_m(t),   t = 1..L chips,
where c_m are mutually orthogonal, zero-mean Walsh-Hadamard codes agreed before the
event (no run-time communication), and z_km in [-1, 1] are the zone's normalised
weighted statistics. In the droop steady state of an island the frequency deviation is

    dw(t) = [ sum_k p_k(t) + dP_base(t) - P_loss(t) ] / sum_k D_k ,

so the network *computes* the sum of all pilots physically. Every zone correlates its own
local frequency measurement with each code:  y_m = (1/L) sum_t c_m(t) dw(t)
                                               = A * sum_k z_km / sum_k D_k  + noise.
The unknown, time-varying aggregate droop stiffness sum_k D_k (inverter trips, SoC-adaptive
gains) and the unknown network are cancelled by taking a ratio of two code correlations:

    x_hat = y_num / y_den = sum_k w_k x_k / sum_k w_k      (precision-weighted average).

Constant and slowly drifting load imbalance is rejected because the codes are zero-mean
and high-sequency. Only the aggregate ever appears on the physical channel.
"""
import numpy as np
from scipy.linalg import hadamard


def drift_order(length):
    """Polynomial drift-rejection order of every Sylvester-Hadamard row: row i is orthogonal to
    t^j for all j < popcount(i) (Proposition 2), so it rejects drift of degree < popcount(i)."""
    return np.array([bin(i).count("1") for i in range(length)])


def walsh_codes(n_codes, length=64, order="drift"):
    """Return n_codes orthogonal, zero-mean +/-1 codes of the given length.

    order="drift" (default, proposed): rows with the highest polynomial drift-rejection order
    (popcount of the row index) first, ties broken by sequency, so that every code used is exactly
    orthogonal to load/PV drift of degree < q_min (q_min = 5 for 13 codes of length 128).
    order="sequency" (v1.0 behaviour): highest sequency first; the first code then rejects only
    constants. The all-ones (DC) row is never used."""
    H = hadamard(length)
    seq = (np.diff(H, axis=1) != 0).sum(axis=1)
    if order == "sequency":
        idx = [i for i in np.argsort(-seq) if seq[i] > 0]
    elif order == "drift":
        q = drift_order(length)
        idx = [i for i in sorted(range(length), key=lambda i: (-q[i], -seq[i])) if seq[i] > 0]
    else:
        raise ValueError(order)
    if n_codes > len(idx):
        raise ValueError("not enough codes for this length")
    return H[idx[:n_codes]].astype(float)


def code_drift_order(C):
    """Largest q such that every row of C is orthogonal to t^j, j < q (numerical check)."""
    L = C.shape[1]; t = np.arange(L) / L
    q = 0
    while q < 12 and np.max(np.abs(C @ t ** q)) < 1e-9 * L:
        q += 1
    return q


class RCDChannel:
    """Book-keeping for one aggregation round.

    quantities: list of (name, scale, weighted) - 'weighted' quantities carry their own
    denominator code (precision weights); unweighted ones share the common 'ones' code.
    """

    def __init__(self, quantities, length=64, amplitude_mw=0.010, code_order="drift"):
        self.q = quantities
        self.names = [q[0] for q in quantities]
        self.num_code = {}
        self.den_code = {}
        m = 0
        self.ones = m; m += 1
        for name, scale, weighted in quantities:
            self.num_code[name] = m; m += 1
            if weighted:
                self.den_code[name] = m; m += 1
            else:
                self.den_code[name] = self.ones
        self.n_codes = m
        self.C = walsh_codes(m, length, order=code_order)
        self.L = length
        self.A = amplitude_mw
        self.scale = {q[0]: q[1] for q in quantities}

    def contributions(self, values, weights=None, wmax=None, dp_sigma=0.0, rng=None):
        """values: dict name -> array (N,), weights: dict name -> array (N,) for weighted
        quantities. Returns Z (N x n_codes) in [-1, 1] (plus optional Gaussian dither)."""
        N = len(next(iter(values.values())))
        Z = np.zeros((N, self.n_codes))
        Z[:, self.ones] = 0.5
        for name, scale, weighted in self.q:
            x = np.clip(np.asarray(values[name]) / scale, -1, 1)
            if weighted:
                w = np.clip(np.asarray(weights[name]) / wmax[name], 0, 1)
                Z[:, self.num_code[name]] = w * x
                Z[:, self.den_code[name]] = w
            else:
                Z[:, self.num_code[name]] = 0.5 * x
        if dp_sigma > 0:
            Z = Z + rng.normal(0, dp_sigma, Z.shape)
        return Z

    def pilot_powers(self, Z):
        """Pilot power of every zone on every chip (MW): N x L."""
        return self.A * Z @ self.C

    def decode(self, dw_series):
        """dw_series: (L,) measured frequency deviation at one zone. Returns dict name -> estimate."""
        y = self.C @ dw_series / self.L
        out = {}
        for name in self.names:
            den = y[self.den_code[name]]
            num = y[self.num_code[name]]
            out[name] = (num / den) * self.scale[name] if abs(den) > 1e-12 else np.nan
        return out, y


def linear_channel(P_pilot, D_total, rng, load_sigma_mw=0.0125, drift_mw=0.01, pll_sigma_hz=0.001,
                   n_listeners=1, f0=60.0, loss_coeff=0.0, ramp_mw=0.0, curv_mw=0.0):
    """Fast droop-channel model validated against the AC droop power flow (Exp. 1).
    P_pilot: N x L pilot powers. Returns n_listeners x L frequency deviations (pu).
    ramp_mw / curv_mw: deterministic net-load change over the round (linear part, end-to-end) and
    its quadratic bow, e.g. a PV ramp (Exp. 7). Default 0 reproduces v1.0 exactly."""
    N, L = P_pilot.shape
    tot = P_pilot.sum(0)
    load = rng.normal(0, load_sigma_mw, L) + drift_mw * np.linspace(-1, 1, L) * rng.normal()
    if ramp_mw or curv_mw:
        u = np.linspace(-1, 1, L)
        load = load + 0.5 * ramp_mw * u + curv_mw * (u ** 2 - np.mean(u ** 2))
    dw = (tot - load - loss_coeff * tot ** 2) / D_total
    meas = dw[None, :] + rng.normal(0, pll_sigma_hz / f0, (n_listeners, L))
    return meas


def zcdp_epsilon(sensitivity, sigma, n_releases, delta=1e-5):
    """(epsilon, delta)-DP of n Gaussian releases via zero-concentrated DP composition."""
    rho = n_releases * sensitivity ** 2 / (2 * sigma ** 2)
    return rho + 2 * np.sqrt(rho * np.log(1 / delta))
