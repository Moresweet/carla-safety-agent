import unittest

from carla_safety_agent.generator import GenerationRequest, ScenarioGenerator


class GeneratorTests(unittest.TestCase):
    def test_reproducible(self):
        request = GenerationRequest(count=4, master_seed=19)
        one = [s.to_dict() for s in ScenarioGenerator().generate(request)]
        two = [s.to_dict() for s in ScenarioGenerator().generate(request)]
        self.assertEqual(one, two)
        self.assertEqual(len({s["scenario_id"] for s in one}), 4)

    def test_families_have_expected_behaviour(self):
        for family, expected in (("cut_in", "cut_in"), ("hard_brake", "hard_brake"),
                                 ("occluded_crossing", "cross_road")):
            spec = ScenarioGenerator().generate(GenerationRequest(family=family, count=1))[0]
            self.assertEqual(spec.adversaries[0].behavior, expected)


if __name__ == "__main__":
    unittest.main()
