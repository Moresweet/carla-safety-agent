from setuptools import find_packages, setup

package_name = "carla_safety_visualization"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/rviz", ["rviz/carla_safety.rviz"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    entry_points={"console_scripts": ["bridge = carla_safety_visualization.bridge:main"]},
)
