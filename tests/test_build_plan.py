import unittest
from dataclasses import replace

from carla_safety_agent.build_plan import build_plan
from carla_safety_agent.natural_language import NaturalLanguageCompiler


class BuildPlanTests(unittest.TestCase):
    def test_plan_does_not_mutate_source_and_lists_all_hazard_actors(self):
        source = NaturalLanguageCompiler().compile('Town04 前车急刹').scenario
        other = replace(source.adversaries[0], role='second', trigger_distance_m=30)
        spec = replace(source, family='road_hazard', adversaries=(*source.adversaries, other))
        plan = build_plan(spec)
        self.assertEqual(len(plan.actors), 3)
        self.assertEqual([r['role'] for r in plan.trigger['actors']], [source.adversaries[0].role, 'second'])
        plan.actors[0]['speed_mps'] = 999
        self.assertNotEqual(spec.ego.speed_mps, 999)

    def test_plan_exposes_trigger_and_render_contract(self):
        spec = NaturalLanguageCompiler().compile("Town04 前车急刹，自车 15 m/s").scenario
        plan = build_plan(spec)
        self.assertEqual(plan.interaction, "rear_end")
        self.assertEqual(plan.trigger["action"], "hard_brake")
        self.assertEqual(plan.render["camera"], "ego_chase_rgb")


if __name__ == "__main__":
    unittest.main()
