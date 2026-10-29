"""terrain-policy/1 exact predicates (CONTRACTS.md section 4).

Both the engine's predicates (filter, exact expansion, Fraction) and the verifier's own
exact orientation are compared with rational arithmetic on near-degenerate inputs.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np
import pytest

from solar_terrain.predicates import ExactStats, gradient_exceeds, orient_fraction, orient_sign, segments_meet_open_convex, triangles_meet_open_convex
from solar_terrain.verify import _Exact, _segment_meets_open_quad


def _adversarial(n: int, seed: int):
    rng = np.random.default_rng(seed)
    base = rng.uniform(-1e7, 1e7, (n, 2)) * rng.choice([1.0, 1e-3, 1e-6], (n, 1))
    d = rng.uniform(-10, 10, (n, 2))
    t = rng.uniform(-3, 3, n)
    a, b = base, base + d
    c = base + t[:, None] * d
    c = c + np.spacing(c) * rng.integers(-2, 3, c.shape)
    k = rng.integers(-4, 5, (n, 3))
    # exactly collinear dyadic grid points as well
    g = rng.uniform(-1e6, 1e6, (n, 2))
    step = 2.0 ** rng.integers(-10, 3, (n, 1))
    a2, b2, c2 = g + k[:, :1] * step, g + k[:, 1:2] * step, g + k[:, 2:] * step
    return np.concatenate([a, a2]), np.concatenate([b, b2]), np.concatenate([c, c2])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_engine_orientation_is_exact(seed):
    a, b, c = _adversarial(20_000, seed)
    stats = ExactStats()
    s = orient_sign(a[:, 0], a[:, 1], b[:, 0], b[:, 1], c[:, 0], c[:, 1], stats)
    assert stats.expansion > 0  # the exact stage was exercised
    zeros = 0
    for k in range(0, len(s), 7):
        e = orient_fraction(a[k], b[k], c[k])
        assert s[k] == e, k
        zeros += e == 0
    assert zeros > 0


def test_engine_orientation_tiny_coordinates_use_rationals():
    a = np.array([[1e-300, 1e-300]])
    b = np.array([[2e-300, 2e-300]])
    c = np.array([[3e-300, 3e-300 * (1 + 2**-52)]])
    stats = ExactStats()
    s = orient_sign(a[:, 0], a[:, 1], b[:, 0], b[:, 1], c[:, 0], c[:, 1], stats)
    assert s[0] == orient_fraction(a[0], b[0], c[0]) and stats.fraction == 1


@pytest.mark.parametrize("seed", [4, 5])
def test_verifier_orientation_is_exact(seed):
    a, b, c = _adversarial(5_000, seed)
    ex = _Exact()
    s = ex.orient(a[:, 0], a[:, 1], b[:, 0], b[:, 1], c[:, 0], c[:, 1])
    for k in range(0, len(s), 3):
        assert s[k] == orient_fraction(a[k], b[k], c[k]), k


def test_segment_and_triangle_tests_agree_between_engine_and_verifier():
    rng = np.random.default_rng(7)
    quad = np.array([[2.0, 3.0], [6.0, 3.0], [6.0, 5.0], [2.0, 5.0]])
    qq = [(Fraction(x), Fraction(y)) for x, y in quad]
    # endpoints snapped to a 0.5 m lattice so that touching, collinear and corner cases are common
    seg = rng.integers(0, 17, (3000, 2, 2)) * 0.5
    seg = seg[(seg[:, 0] != seg[:, 1]).any(axis=1)]
    eng = segments_meet_open_convex(seg, quad)
    for k in range(len(seg)):
        p = (Fraction(seg[k, 0, 0]), Fraction(seg[k, 0, 1]))
        q = (Fraction(seg[k, 1, 0]), Fraction(seg[k, 1, 1]))
        assert eng[k] == _segment_meets_open_quad(p, q, qq), seg[k]
    edge = np.array([[[2.0, 3.0], [6.0, 3.0]], [[0.0, 3.0], [9.0, 3.0]], [[4.0, 0.0], [4.0, 3.0]], [[4.0, 0.0], [4.0, 3.5]]])
    assert segments_meet_open_convex(edge, quad).tolist() == [False, False, False, True]
    tri = np.array([[[2.0, 1.0], [6.0, 1.0], [4.0, 3.0]], [[2.0, 1.0], [6.0, 1.0], [4.0, 3.0000001]], [[6.0, 5.0], [8.0, 5.0], [8.0, 7.0]]])
    assert triangles_meet_open_convex(tri, quad).tolist() == [False, True, False]


def test_slope_decision_is_exact_at_the_threshold():
    t = float(np.tan(np.radians(26.56505117707799)))  # ~0.5
    tri = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.5]]])  # gradient exactly 0.5
    expect = Fraction(1, 4) > Fraction(t) ** 2
    assert bool(gradient_exceeds(tri, t)[0]) == expect
    assert bool(gradient_exceeds(tri, 0.5)[0]) is False  # equality is within the limit
    assert bool(gradient_exceeds(tri, float(np.nextafter(0.5, 0)))[0]) is True
