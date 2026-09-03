import json
import tempfile
import unittest
from pathlib import Path

from carla_safety_agent.e2e_benchmark import parse_bench2drive_results


class EndToEndBenchmarkTests(unittest.TestCase):
    def test_collision_is_ranked_above_clean_route(self):
        records = [
            {"route_id": "clean", "status": "Completed", "scenario_name": "A", "town_name": "T",
             "scores": {"score_route": 100, "score_composed": 100}, "infractions": {}},
            {"route_id": "collision", "status": "Completed", "scenario_name": "B", "town_name": "T",
             "scores": {"score_route": 100, "score_composed": 50},
             "infractions": {"collisions_vehicle": ["hit"]}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            path.write_text(json.dumps({"_checkpoint": {"records": records}}))
            ranked = parse_bench2drive_results(path)
        self.assertEqual(ranked[0].route_id, "collision")
        self.assertEqual(ranked[0].collisions, 1)
        self.assertEqual(ranked[-1].criticality_score, 0.0)


if __name__ == "__main__":
    unittest.main()
