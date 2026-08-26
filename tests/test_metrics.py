import unittest

from carla_safety_agent.metrics import KinematicState, evaluate, ttc
from carla_safety_agent.models import OracleSpec


class MetricsTests(unittest.TestCase):
    def test_ttc_for_closing_pair(self):
        ego = KinematicState(0, 0, 10, 0)
        lead = KinematicState(20, 0, 5, 0)
        self.assertAlmostEqual(ttc(ego, lead), 4.0)

    def test_ttc_none_when_separating(self):
        self.assertIsNone(ttc(KinematicState(0, 0, 5, 0), KinematicState(20, 0, 10, 0)))

    def test_oracle_marks_critical(self):
        result = evaluate("x", OracleSpec(), False, 0.8, 2.0, 3.0)
        self.assertEqual(result.status, "critical")
        self.assertIn("ttc_below_threshold", result.failure_reasons)


if __name__ == "__main__":
    unittest.main()
