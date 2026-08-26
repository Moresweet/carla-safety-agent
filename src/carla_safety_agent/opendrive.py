from __future__ import annotations

import math
from xml.etree import ElementTree as ET

from .models import GeneratedMapSpec


def build_opendrive(spec: GeneratedMapSpec) -> str:
    """Compile a segment-level road contract into CARLA-compatible OpenDRIVE."""
    root = ET.Element("OpenDRIVE")
    total_length = sum(segment.length_m for segment in spec.segments)
    ET.SubElement(root, "header", {
        "revMajor": "1", "revMinor": "4", "name": spec.name,
        "version": "1.00", "date": "2026-08-26",
        "north": "10000", "south": "-10000", "east": "10000", "west": "-10000",
        "vendor": "carla-safety-agent",
    })
    road = ET.SubElement(root, "road", {
        "name": spec.name, "length": _number(total_length), "id": "1", "junction": "-1",
    })
    ET.SubElement(road, "link")
    road_type = ET.SubElement(road, "type", {"s": "0", "type": "rural"})
    ET.SubElement(road_type, "speed", {"max": _number(spec.speed_limit_mps), "unit": "m/s"})
    plan = ET.SubElement(road, "planView")
    s = x = y = heading = 0.0
    for segment in spec.segments:
        geometry = ET.SubElement(plan, "geometry", {
            "s": _number(s), "x": _number(x), "y": _number(y),
            "hdg": _number(heading), "length": _number(segment.length_m),
        })
        if segment.kind == "line":
            ET.SubElement(geometry, "line")
            x += segment.length_m * math.cos(heading)
            y += segment.length_m * math.sin(heading)
        else:
            ET.SubElement(geometry, "arc", {"curvature": _number(segment.curvature)})
            end_heading = heading + segment.curvature * segment.length_m
            x += (math.sin(end_heading) - math.sin(heading)) / segment.curvature
            y += (-math.cos(end_heading) + math.cos(heading)) / segment.curvature
            heading = end_heading
        s += segment.length_m
    elevation = ET.SubElement(road, "elevationProfile")
    ET.SubElement(elevation, "elevation", {"s": "0", "a": "0", "b": "0", "c": "0", "d": "0"})
    ET.SubElement(road, "lateralProfile")
    lanes = ET.SubElement(road, "lanes")
    ET.SubElement(lanes, "laneOffset", {"s": "0", "a": "0", "b": "0", "c": "0", "d": "0"})
    section = ET.SubElement(lanes, "laneSection", {"s": "0"})
    left = ET.SubElement(section, "left")
    for lane_id in range(1, spec.lanes_each_direction + 1):
        _lane(left, lane_id, spec.lane_width_m)
    center = ET.SubElement(section, "center")
    center_lane = ET.SubElement(center, "lane", {"id": "0", "type": "none", "level": "false"})
    ET.SubElement(center_lane, "link")
    ET.SubElement(center_lane, "roadMark", {
        "sOffset": "0", "type": "solid", "weight": "standard",
        "color": "yellow", "width": "0.15", "laneChange": "none",
    })
    right = ET.SubElement(section, "right")
    for lane_id in range(-1, -spec.lanes_each_direction - 1, -1):
        _lane(right, lane_id, spec.lane_width_m)
    ET.SubElement(road, "objects")
    ET.SubElement(road, "signals")
    return '<?xml version="1.0" standalone="yes"?>\n' + ET.tostring(root, encoding="unicode")


def _lane(parent: ET.Element, lane_id: int, width: float) -> None:
    lane = ET.SubElement(parent, "lane", {"id": str(lane_id), "type": "driving", "level": "false"})
    ET.SubElement(lane, "link")
    ET.SubElement(lane, "width", {"sOffset": "0", "a": _number(width), "b": "0", "c": "0", "d": "0"})
    ET.SubElement(lane, "roadMark", {
        "sOffset": "0", "type": "broken", "weight": "standard",
        "color": "white", "width": "0.12", "laneChange": "both",
    })


def _number(value: float) -> str:
    return f"{value:.9g}"
