import unittest

from carla_safety_agent.natural_language import DescriptionError, NaturalLanguageCompiler


class NaturalLanguageTests(unittest.TestCase):
    def test_chinese_rear_end_with_units(self):
        result = NaturalLanguageCompiler().compile(
            "在 Town04 大雨夜间，自车以 72 km/h 跟随前车，前车以 36 km/h 行驶并突然急刹"
        )
        self.assertEqual(result.scenario.family, "rear_end")
        self.assertAlmostEqual(result.scenario.ego.speed_mps, 20.0)
        self.assertAlmostEqual(result.scenario.adversaries[0].speed_mps, 10.0)
        self.assertEqual(result.scenario.environment.precipitation, 70.0)
        self.assertLess(result.scenario.environment.sun_altitude_angle, 0)

    def test_vru(self):
        result = NaturalLanguageCompiler().compile("Town03 有行人横穿道路，自车速度 12 m/s")
        self.assertEqual(result.scenario.family, "vulnerable_road_user")
        self.assertTrue(result.scenario.adversaries[0].blueprint.startswith("walker"))

    def test_unsupported_description_fails(self):
        with self.assertRaises(DescriptionError):
            NaturalLanguageCompiler().compile("阳光明媚的普通巡航")

    def test_fallen_cargo_compiles_generated_asset(self):
        result = NaturalLanguageCompiler().compile(
            "Town04 高速公路前方 40 米有掉落货物，6 根金属管，自车速度 72 km/h"
        )
        self.assertEqual(result.scenario.family, "road_hazard")
        self.assertEqual(result.scenario.adversaries, ())
        asset = result.scenario.generated_assets[0]
        self.assertEqual(asset.shape, "metal_pipes")
        self.assertEqual(asset.count, 6)
        self.assertEqual(asset.distance_ahead_m, 40.0)
        self.assertAlmostEqual(result.scenario.ego.speed_mps, 20.0)
        self.assertEqual(result.extracted["generated_asset"]["count"], 6)

    def test_ambiguous_description_fails(self):
        with self.assertRaises(DescriptionError):
            NaturalLanguageCompiler().compile("前车急刹，同时一辆车从匝道汇入")


if __name__ == "__main__":
    unittest.main()
