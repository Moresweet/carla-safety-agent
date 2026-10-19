"""Run the explicitly selected local acceptance cases serially; stop on failure."""
import subprocess
import sys

NODE = '/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
CASES = [
    ('自然语言 Blender 导出资产的 Unreal 导入、注册、生成与重复导入保护', ['tools/regression_asset_import.py', '--job-id', '5a42ab78732e', '--require-inherited-lock']),
    ('车辆真实 UV、浏览器编辑与场景对照', ['tools/regression_pedestrian_uv.py', '--node', NODE, '--vehicle', '--restart-bridge']),
    ('行人真实 UV、浏览器编辑与场景对照', ['tools/regression_pedestrian_uv.py', '--node', NODE, '--restart-bridge']),
    ('独立自动驾驶采集与传感器清理', ['tools/regression_sensor_rig.py', '--mode', 'autopilot']),
    ('批量任务响应丢失、停止和显式重试', ['tools/regression_batch_lost_response.py', '--stop-retry']),
    ('VAD 跨 Town05 和 Town04 地图真实闭环', ['tools/regression_map_transition.py', '--model', 'vad']),
]

if __name__ == '__main__':
    for name, command in CASES:
        result = subprocess.run([sys.executable, 'tools/run_acceptance_command.py', '--name', name, '--', sys.executable, *command])
        if result.returncode:
            raise SystemExit(result.returncode)
