"""Exact counterexamples for the advanced fixture; no Jev API calls."""
import json
from pathlib import Path
import unittest

import sympy as s

from jevtex.tex import extract

ROOT = Path(__file__).resolve().parents[1]


class MatrixSampleTests(unittest.TestCase):
    def test_fixture_pairs(self):
        source = (ROOT / "examples/matrix_calculus_mistake.tex").read_text()
        parsed = extract(source)
        truth = json.loads((ROOT / "examples/matrix_calculus_expected.json").read_text())
        pairs = truth["variants"]["mistake"]
        self.assertEqual(parsed["warnings"], [])
        self.assertEqual(len(parsed["equations"]), 11)
        self.assertEqual(parsed["pairs"], [
            {k: p[k] for k in ("before", "after", "context_ids")} for p in pairs
        ])
        self.assertEqual([p["after"] for p in pairs if p["expected"] == "incorrect"],
                         ["e3", "e6", "e10"])
        for index, formula in ((2, r"\frac{X^{n-1}H}{(n-1)!}"),
                               (5, "A^2B-2ABA-BA^2"),
                               (9, r"\operatorname{tr}(X^{-2}KH)")):
            self.assertIn(formula, parsed["equations"][index]["latex"])

    def test_exact_matrix_calculus(self):
        t, u = s.symbols("t u", real=True)
        X, H = s.diag(1, 0), s.Matrix([[0, 1], [0, 0]])
        actual = (X + t * H).exp().diff(t).subs(t, 0)
        self.assertEqual(actual, (s.E - 1) * H)
        self.assertEqual(X.exp() * H, s.E * H)
        self.assertNotEqual(actual, X.exp() * H)
        for n in range(1, 5):
            product_rule = sum((X**k * H * X**(n-1-k) for k in range(n)), s.zeros(2))
            self.assertEqual(((X+t*H)**n).diff(t).subs(t, 0), product_rule)
        n = s.symbols("n", integer=True, positive=True)
        self.assertEqual(s.summation(1/s.factorial(n-1), (n, 1, s.oo)), s.E)

        A, B = s.symbols("A B", commutative=False)
        self.assertEqual(s.expand(A*(A*B-B*A)-(A*B-B*A)*A), A**2*B-2*A*B*A+B*A**2)
        A, B = s.diag(1, 2), H
        actual = ((t*A).exp() * B * (-t*A).exp()).diff(t, 2).subs(t, 0)
        wrong = A**2*B-2*A*B*A-B*A**2
        self.assertEqual(actual, B)
        self.assertEqual(wrong, -7*B)
        self.assertEqual((B+t*(A*B-B*A)+t**2/2*wrong).diff(t, 2), wrong)

        X, H = s.diag(1, 2), s.Matrix([[0, 1], [1, 0]])
        actual = s.diff(s.log((X+t*H).det()), t, 2).subs(t, 0)
        self.assertEqual(actual, -1)
        self.assertEqual(-s.trace(X.inv()*H*X.inv()*H), actual)
        self.assertEqual(-s.trace(X**-2 * H**2), -s.Rational(5, 4))
        a, b, c = s.symbols("a b c", real=True)
        K = s.Matrix([[a, b], [b, c]])
        mixed = s.diff(s.log((X+t*H+u*K).det()), t, u).subs({t: 0, u: 0})
        self.assertEqual(s.simplify(mixed + s.trace(X.inv()*K*X.inv()*H)), 0)
        self.assertEqual((-s.trace(X**-2*K*H)).subs({a: 0, b: 1, c: 0}),
                         -s.trace(X**-2*H**2))


if __name__ == "__main__":
    unittest.main()
