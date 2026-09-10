import json
import tempfile
import unittest
from pathlib import Path

from carla_safety_agent.benchmark_catalog import algorithm_catalog
from carla_safety_agent.e2e_benchmark import parse_bench2drive_results


class EndToEndBenchmarkTests(unittest.TestCase):
    def test_algorithm_catalog_resolves_both_official_branches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zoo, tcp_zoo = root / "zoo", root / "tcp"
            required = [
                zoo / "team_code/uniad_b2d_agent.py",
                zoo / "ckpts/uniad_tiny_b2d.pth",
                zoo / "adzoo/uniad/configs/stage2_e2e/tiny_e2e_b2d.py",
                tcp_zoo / "team_code/tcp_b2d_agent.py",
                tcp_zoo / "ckpts/tcp_b2d.ckpt",
            ]
            for path in required:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            entries = {item["id"]: item for item in algorithm_catalog(zoo, tcp_zoo)}
        self.assertEqual(entries["uniad-tiny"]["status"], "available")
        self.assertEqual(entries["tcp"]["status"], "available")
        self.assertEqual(entries["tcp"]["sensors"], "3 cameras")
        self.assertEqual(entries["admlp"]["status"], "not_installed")
        self.assertEqual(entries["driveadapter"]["status"], "not_integrated")

    def test_unsupported_adapter_does_not_become_runnable_from_filenames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for model in ('driveadapter', 'thinktwice'):
                for name in (f'team_code/{model}_b2d_agent.py', f'ckpts/{model}_b2d.pth'):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('not a working integration')
            entries = {item['id']: item for item in algorithm_catalog(root)}
            for model in ('driveadapter', 'thinktwice'):
                self.assertEqual(entries[model]['status'], 'not_integrated')
                self.assertFalse(entries[model]['integration_supported'])
                self.assertEqual(entries[model]['missing_files'], [])

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
