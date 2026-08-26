import unittest
from xml.etree import ElementTree as ET

from carla_safety_agent.models import GeneratedMapSpec, RoadSegmentSpec
from carla_safety_agent.opendrive import build_opendrive


class OpenDriveTests(unittest.TestCase):
    def test_s_curve_compiles_valid_opendrive(self):
        spec = GeneratedMapSpec("test", (
            RoadSegmentSpec("line", 40),
            RoadSegmentSpec("arc", 50, 0.015),
            RoadSegmentSpec("arc", 50, -0.015),
            RoadSegmentSpec("line", 60),
        ))
        root = ET.fromstring(build_opendrive(spec))
        road = root.find("road")
        self.assertEqual(float(road.attrib["length"]), 200.0)
        self.assertEqual(len(root.findall("./road/planView/geometry")), 4)
        self.assertEqual(len(root.findall("./road/lanes/laneSection/left/lane")), 2)
        self.assertEqual(len(root.findall("./road/lanes/laneSection/right/lane")), 2)


if __name__ == "__main__":
    unittest.main()
