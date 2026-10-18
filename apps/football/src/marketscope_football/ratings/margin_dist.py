"""Key-number-aware margin distribution (MS-032, selection_design.py): P(margin = k | expected m) is a
normal kernel on the integers re-weighted by multipliers for |k| <= KEY_MAX (3, 7, 10, 6, 14 ... and
ties), shape fitted on 1999-2015 closing lines and scale refitted for the model on 2016-22. It turns an
expected margin into win, cover and push probabilities."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .selection_design import KEY_MAX, MARGIN_SUPPORT

K = np.arange(-MARGIN_SUPPORT, MARGIN_SUPPORT + 1)


@dataclass
class MarginDistribution:
    scale: float
    weights: list[float]  # multipliers for |k| = 0..KEY_MAX

    def _w(self) -> np.ndarray:
        w = np.ones(len(K))
        a = np.abs(K)
        inside = a <= KEY_MAX
        w[inside] = np.asarray(self.weights)[a[inside]]
        return w

    def pmf(self, m: np.ndarray) -> np.ndarray:
        """Rows: P(margin = k) over K for each expected margin."""
        m = np.atleast_1d(np.asarray(m, float))
        z = (K[None, :] - m[:, None]) / self.scale
        p = np.exp(-0.5 * z ** 2) * self._w()[None, :]
        return p / p.sum(axis=1, keepdims=True)

    def p_home(self, m) -> np.ndarray:
        p = self.pmf(m)
        return p[:, K > 0].sum(axis=1) + 0.5 * p[:, K == 0].sum(axis=1)

    def p_cover(self, m, line) -> tuple[np.ndarray, np.ndarray]:
        """P(home margin > line) and P(margin == line) (a push, integer lines only)."""
        p = self.pmf(m)
        line = np.atleast_1d(np.asarray(line, float))
        above = (K[None, :] > line[:, None]).astype(float)
        push = (K[None, :] == line[:, None]).astype(float)
        return (p * above).sum(axis=1), (p * push).sum(axis=1)


def _nll(dist: MarginDistribution, m: np.ndarray, k: np.ndarray) -> float:
    p = dist.pmf(m)
    idx = np.clip(k.astype(int) + MARGIN_SUPPORT, 0, len(K) - 1)
    return float(-np.sum(np.log(np.clip(p[np.arange(len(m)), idx], 1e-12, None))))


def fit_shape(m: np.ndarray, k: np.ndarray) -> tuple[MarginDistribution, dict]:
    """Scale and key-number multipliers by maximum likelihood (log-parameterised)."""
    def unpack(z):
        return MarginDistribution(math.exp(z[0]), list(np.exp(z[1:])))

    z0 = np.concatenate([[math.log(13.5)], np.zeros(KEY_MAX + 1)])
    res = minimize(lambda z: _nll(unpack(z), m, k), z0, method="L-BFGS-B")
    return unpack(res.x), {"converged": bool(res.success), "nll": float(res.fun), "games": int(len(m))}


def fit_scale(shape: MarginDistribution, m: np.ndarray, k: np.ndarray) -> MarginDistribution:
    res = minimize(lambda z: _nll(MarginDistribution(math.exp(z[0]), shape.weights), m, k),
                   np.array([math.log(shape.scale)]), method="L-BFGS-B")
    return MarginDistribution(float(math.exp(res.x[0])), list(shape.weights))
