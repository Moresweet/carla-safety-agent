import unittest

from carla_safety_agent.build_plan import build_plan
from carla_safety_agent.natural_language import NaturalLanguageCompiler


class BuildPlanTests(unittest.TestCase):
    def test_plan_exposes_trigger_and_render_contract(self):
        spec = NaturalLanguageCompiler().compile("Town04 前车急刹，自车 15 m/s").scenario
        plan = build_plan(spec)
        self.assertEqual(plan.interaction, "rear_end")
        self.assertEqual(plan.trigger["action"], "hard_brake")
        self.assertEqual(plan.render["camera"], "ego_chase_rgb")


if __name__ == "__main__":
    unittest.main()
