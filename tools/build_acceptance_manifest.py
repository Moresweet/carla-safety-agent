"""Assemble the September 14 local audit from retained, dated evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V = ROOT / 'runs/validation'

def relative(path):
    return str(Path(path).relative_to(ROOT))

def main():
    cases = []
    overview = V / 'browser-models-8f0cb982-e674-4cb5-ba24-e238e74069ba'
    cases.append(dict(title='页面入口、模型可用状态、资产检索和自然语言基本体导出', state='passed',
        steps='逐个打开六个一级页面；检查五个可用模型和两个禁用模型；检索资产；预览自然语言结构化模型计划后实际调用 Blender 导出。',
        observed='页面可访问，资产检索与计划确认有效；生成蓝色长方体，保留 blend、GLB 和 FBX。',
        limits='页面截图证明入口可访问，不代表该页全部能力已完成。自然语言生成目前是有边界的结构化基本体，不是任意复杂模型或道路城市生成。',
        images=[relative(p) for p in sorted(overview.glob('*.png'))]))
    notes = {
        'b6a15992bc354c0584c1c5173332b79a': ('创建受控未知来源对象，重启桥接并使用来源筛选。', '未知来源没有被伪装成地图原生对象；来源筛选通过，测试对象已清理。', '来源区分依赖受管记录；不能追溯任意外部历史操作。'),
        '2370759da9674ad8b37836fd38fa99f3': ('两对象位置修改、草稿保护、撤销重做、桥接重启、未执行意图恢复检查。', '目标对象历史可追溯；对照对象不变；待处理意图需明确检查，不自动重放。', '仅位置历史；不是所有生成、删除及逐笔涂绘的全局撤销。'),
        'd60d85e1a3b44e2fa8c41dcbd252b048': ('局部修订预览、取消、采纳、重新确认后运行规则场景并采集。', '非法描述被拒绝；预览不修改世界；规则执行和 20 帧原始数据校验通过。', '支持明确字段，不是任意自然语言语义或完整地图生成。'),
        '9b158e1318804e9a99618af478f4675b': ('依次运行 VAD、TCP、AD-MLP、UniAD-Tiny、UniAD-Base，校验真实模型输入、辅助采集、预测标签和退出清理。', '五个模型通过；分别保存 20、20、60、20、20 帧，总计 140 帧。TCP 首帧预热；AD-MLP 21 帧预热、4 帧新预测、35 帧复用预测，未把复用冒充新推理。', '每项为 1 秒仿真（AD-MLP 3 秒）加实景预览；这是接入/生命周期短回归，不是长距离驾驶性能验收。17/18 传感器外参可验证，不以缺失项冒充全标定；预测时间间隔未验证，未计算 ADE/FDE。'),
        '3604d75ff735438d8b97c57cbcdd9ef6': ('复用本轮自然语言导出的指定资产，原生导入、注册、生成，重复导入同名资产。', '蓝色长方体在 CARLA 中实际可见；子进程继承导入锁；同名重复导入被拒绝并留存可追溯记录。', '新增唯一命名测试源资产/注册资产保留，临时场景对象已清理。部分失败记录保留，不等于整个资产链具备原子回滚。'),
        'b307087ceb394cd5b0618545a35808a1': ('生成目标和对照 Audi A2，重启桥接，浏览器上传方向棋盘格、检查源 UV、应用并比较实景。', '目标车身材质正确出现棋盘格，对照车辆未修改；截图包含编辑器和高亮消失后的实景。', '只覆盖 Audi A2 车身；不能推广为全部车辆、全部材质槽。'),
        'c5bc172fac58495f9daeefe0dae6630c': ('生成目标和对照行人，读取真实网格及 slot 14 UV，浏览器应用方向棋盘格并对照实景。', 'walker.pedestrian.0001 裤子棋盘格可见，其余区域和对照对象未修改。', '只覆盖该行人的裤子槽，不是所有行人、衣服布局和动画状态。'),
        '92e7b4a8e11447ab817ff5a6c914001b': ('独立规则驾驶运行 120 帧，每 3 帧保存，拒绝重复启动并检查退出清理。', '40 个同步样本、14/14 外参校验；车辆实际移动，传感器与 Traffic Manager 所有权清理通过。', '独立输入文件是 sensor_input.npz，不是模型输入。此次未重新测试手动键盘控制和强杀故障恢复全部分支。'),
        '503d66229d0a4c6a837538ef045ba4bd': ('两项规则任务；首项启动成功后丢弃响应，恢复绑定、停止、显式重试，暂停后续调度再恢复。', '没有重复启动；首项保留 stopped 和 completed 两次尝试，第二项一次完成；两项数据与退出状态通过。', '注入的是调用边界响应丢失，不是实际断网或模拟器崩溃；不代表完整纹理 A/B 矩阵。'),
        '638c8bdba8be4569bb989613e7dfdf5e': ('从空闲 Town04 保存快照；VAD 切入 Town05、再切回 Town04，各运行 20 步并保存原始采集，恢复原工作台。', '两次真实世界 ID 均改变；两项执行返回 0；40 帧校验通过，异步模式、零传感器；原编辑快照恢复成功。', '本轮没有复现段错误，但不能证明旧崩溃唯一由切图造成或所有切图均安全。旧世界请求拒绝未规范返回、Vulkan Invalid texture in SRT 警告仍需调查。'),
        'd0c71390c90145948257fd010dfaa865': ('对加油站建筑、长椅、道路分别读取真实 UV、上传棋盘格、应用到指定单槽并恢复原材质。', '详见每个资产的编辑器、应用前、应用后、恢复后三组截图和各自机器记录。', '只覆盖这三个指定静态网格，不是全部环境实例、样条路段或任意共享材质布局。'),
        '4766e75039ba489bb49d99b4fa3692c3': ('保存 Audi A2 棋盘格材质版本，撤销、重做、删除受控测试对象后通过场景恢复重新生成，校验场景包材质哈希。', '版本和重新生成后的材质引用保持；对照对象保持自己的绿色材质；测试对象已清理。', '覆盖受管 Audi A2 车身版本，不是任意资产或所有编辑操作的统一事务。'),
    }
    for path in sorted(V.glob('acceptance-20260914-*/acceptance.json'), key=lambda p: json.loads(p.read_text()).get('started_at', '')):
        report = json.loads(path.read_text())
        if report['state'] == 'running':
            raise RuntimeError('Acceptance still running: ' + str(path))
        key = path.parent.name.removeprefix('acceptance-20260914-')
        steps, observed, limits = notes.get(key, (report['name'],
            '以本节机器记录和原始截图为准；通过仅表示所列脚本断言完成。',
            '代表性本机回归，不涵盖任意地图、资产、故障或跨机器环境。'))
        cases.append(dict(title=report['name'], report=relative(path), steps=steps, observed=observed, limits=limits))
    replay = [
        ('VAD 六视角、深度、轨迹与点云交叉检查', 'bec08f62-c564-4062-b86c-3dd0c089855e'),
        ('TCP 保存回放：真实模型输入与辅助视角区分', '910760a0-478b-45bb-885b-a4ba0add0dd2'),
        ('AD-MLP 保存回放：预热之后的复用预测', '38fc9e97-a275-4a8f-8945-080c0dc87eb9'),
        ('UniAD-Tiny 保存回放', 'd974841c-24e5-4eee-9bb0-39ce75a3714d'),
        ('UniAD-Base 保存回放：稳定后复测', '2a09014e-ac12-42ee-9516-50dd767f0e08'),
        ('VAD 切入 Town05 的保存回放', 'f384f47a-e3cf-43c1-89c1-d43e8ed349b3'),
        ('VAD 切回 Town04 的保存回放', '61cceb5f-fdab-48be-b569-f3d46f985d77'),
    ]
    for title, identifier in replay:
        folder = V / ('browser-models-' + identifier)
        cases.append(dict(title=title, state='passed', steps='选择本轮实际保存数据集，检查六 RGB、六深度以及点云、顶视图、轨迹。',
            observed='浏览器图像加载断言通过；真实轨迹与模型规划空间点分开显示。',
            limits='回放数据不是重新仿真；顶视 RGB 不是语义 BEV 真值。预测点时间间隔未验证，空间叠加不等于完整精度评测。',
            report=relative(folder/'report.json'), images=[relative(p) for p in sorted(folder.glob('*.png'))]))
    cases.append(dict(title='异常记录：桥接重启期间回放深度图加载失败', state='failed（同数据集稳定后复测通过）',
        steps='UniAD-Base 回放恰与车辆测试重启桥接重叠。', observed='六个深度图加载断言失败并出现破图；同一数据集后续复测及磁盘质量扫描通过，未发生 CARLA 进程崩溃。',
        limits='并发重启是相关线索而非已证明的唯一根因；后续需补图片 onError、断连提示、重连后有界重试，并独立注入后端重启验证。',
        images=[relative(V/'browser-models-46149c5e-159a-46ec-966d-19eab7d21779/failure.png')]))
    cases.append(dict(title='ROS 九路可视化插件', state='passed', steps='真实 ROS 发布/订阅鲜活采集帧，Qt 九宫格渲染六 RGB、正前深度、BEV 点云、顶视 RGB。',
        observed='九路收到并显示；截图为真实数据而非设计稿。', limits='首轮在采集结束后没有鲜活帧而等待失败，未篡改时间戳；运行采集时复测通过。本轮不是 RViz 全功能或 TF 树验收。',
        images=[relative(V/'sensor-wall-133e1c6abcbf4c9a99a09e1c76f46004.png')]))
    cases.append(dict(title='批次重试历史页面', state='passed', steps='打开已完成批次并展开首项尝试历史，不重新启动任务。',
        observed='两项分别保留 2 / 1 次尝试；停止记录未被覆盖。',
        images=[relative(V/'browser-models-1039952a-bf67-455f-9e70-399921cf79ec/batch-retry-rows.png')]))
    folder = V/'browser-models-38564e78-44be-458e-a617-54ca56f02941'
    cases.append(dict(title='独立采集保存回放和导入历史最终复测', state='passed', report=relative(folder/'report.json'),
        steps='所有世界写入完成后打开独立采集数据，检查六 RGB、六深度、点云投影、质量检查；展开指定 Blender 任务的导入历史。',
        observed='40 帧保存回放正常，独立摄像头明确标注为非模型输入，不伪造预测。成功和重复导入拒绝记录属于同一指定任务。',
        limits='先前回放在会话 recovering 期间超过测试的 20 秒等待，稳定后通过；页面仍需超时、重试及清晰断连状态。导入历史首次检查因测试脚本误选生成记录失败，已修正为按标题定位并加强同任务断言，未修改产品逻辑。',
        images=[relative(p) for p in sorted(folder.glob('*.png'))]))
    cases.append(dict(title='保留异常证据：恢复期间索引等待与导入测试选择器', state='记录保留，稳定复测通过',
        observed='第一张：独立数据回放索引在 recovering 期间尚未加载；第二张：导入检查脚本误选同 CSS 类的生成记录，失败发生在页面顶部。二者不可混同为 CARLA 崩溃。',
        images=[relative(V/'browser-models-496059f7-ecfb-43fb-9994-e4422befed5f/failure.png'),
                relative(V/'browser-models-231f2af7-2c0a-4ff0-b39c-2b729b0ea403/failure.png')]))
    health_path = max(V.glob('final-health-*/report.json'), key=lambda p:p.stat().st_mtime)
    health = json.loads(health_path.read_text())
    assert health['state'] == 'passed'
    cases.append(dict(title='最终健康、自动化检查和日志边界', report=relative(health_path),
        steps='读取前端 HTTP、预检、会话、连续五秒 CARLA 世界状态，再执行 940 单测、TypeScript、四组 JS 逻辑回归和 diff 检查。',
        observed='所有列出的检查返回成功，Town04 空闲异步、零传感器；服务保留运行。CARLA 追加日志包含历史崩溃，最终记录按 2026-09-14 时间段过滤，不能把旧记录算作今天的新崩溃。',
        limits='告警匹配行数不是故障次数；桥接日志无时间戳，部分条目可能来自历史。Vulkan 警告和旧世界 GET 请求未规范处理仍列入待办。自动化逻辑检查通过机器日志证明，不伪造终端或 GUI 截图。'))
    captions = {'before.jpg':'该项测试前 CARLA 实景', 'after.jpg':'该项测试结束后的 CARLA 实景',
        'target-before.jpg':'目标对象：应用前', 'target-applied.jpg':'目标对象：立即应用后（可能有临时高亮）',
        'target-applied-after-highlight.jpg':'目标对象：高亮结束后的纹理实景',
        'control-before.jpg':'未修改对照对象：测试前', 'control-after.jpg':'未修改对照对象：测试后',
        'applied.jpg':'指定材质槽：应用棋盘格后', 'restored.jpg':'指定材质槽：恢复原材质后',
        'material-atlas.png':'实际提交的方向棋盘格图集（测试输入，不是截图）',
        'material-uv.png':'编辑器真实网格与 UV 预览', 'material-uv-zoom.png':'道路真实网格预览放大检查',
        'six-rgb.png':'六视角 RGB 与点云、顶视图', 'six-depth.png':'六视角米制深度可视化',
        'prediction-overlay.png':'记录轨迹与模型预测的空间叠加', 'depth-diagnostic.png':'深度与点云投影交叉检查',
        'raw-quality.png':'保存数据的原始文件质量检查', 'model-selection.png':'模型选择及计划确认保护'}
    for case in cases:
        case['captions'] = captions
    data = dict(title='CARLA 本机系统测试、功能完成情况与后续开发报告', date='2026-09-14 · Asia/Shanghai',
        scope='本报告区分本轮实际回归、既有实现和未完成能力。截图为测试时保存的原始页面或 CARLA 图像。短测试通过不等于驾驶安全保证、任意资产全覆盖或未来绝不崩溃。',
        summary=['CARLA、前端和桥接已在本机启动；本轮未使用 Docker。最终服务状态见末尾健康检查记录。',
            '五个现有模型短闭环、140 帧原始数据与退出清理通过；ThinkTwice、DriveAdapter 仍未完成原生闭环接入。',
            '940 项 Python 测试通过（6.46 秒），TypeScript 无输出通过，前端生产构建通过；构建器提示路由静态分类 Unknown，不等同于构建失败。',
            f'最终磁盘可用约 {health["disk_free_bytes"]/2**30:.1f} GiB；需在长时间录制之前规划归档或扩容，本次未删除历史数据。',
            '当前整体仍在开发中，不给出缺乏依据的完成百分比。GitHub 推送尚未执行，等待之前请求的明确确认。'],
        features=[
            ['S1 仿真稳定性','现有五模型短生命周期已验证；单会话和退出清理可用','长期压力、强杀/驱动异常和全地图组合仍未完全覆盖；旧 signal 11 栈不足以单独认定唯一根因'],
            ['S2 对象和场景管理','来源筛选、位置草稿、撤销重做及桥接重启保持已验证','不是生成/删除/逐笔绘制统一撤销；跨地图完整场景编辑恢复仍需持续扩大验收'],
            ['S3 UV 和纹理','车辆、行人、建筑、长椅、道路代表资产本轮验证，车辆纹理版本可恢复','不是所有元素均可编辑；实例化、样条及未适配材质布局须拒绝或显式提示；实景光照不同，道路默认预览偏小'],
            ['S4 采集','五模型真实输入与辅助六视角/深度/XYZI/BEV 分开保存；独立采集可用','模型输入数量不同，不能强行统称六相机输入；缺失标定项、存储配额与长期性能需完善'],
            ['S5 回放与 ROS','保存播放、真实轨迹、预测空间叠加和九路 ROS 展示可用','语义 BEV 真值、带可靠时间契约的 ADE/FDE、全 TF 验收未完成；断连图片恢复需补强'],
            ['S6 自然语言和 Blender','计划修改确认、基本体导出、原生导入注册生成已验证','任意复杂 3D/新道路地图生成未实现；完整资产事务回滚未完成'],
            ['S7 实验中心','队列、暂停、停止、显式重试与尝试记录已实现','完整纹理 A/B、驾驶指标和故障矩阵的长期验收未完成'],
            ['模型扩展','ThinkTwice 真实权重严格加载和完整尺寸合成前向已有证据','合成前向不是 CARLA 接入；ThinkTwice 真实传感器/控制链和 DriveAdapter 依赖适配仍待完成'],
            ['S8 迁移','已有本地源包和场景资产包校验机制','旧源包并非当前全部修改；另一台机器冷启动验证和 GitHub 同步未完成'],
        ], next_steps=[
            'P0：补回放图片断连提示与有界重试，做后端重启故障注入；继续多轮启停、跨地图和资源清理压力测试。',
            'P0：在已有单次 20 GiB / 2000 帧、磁盘保留至少 1 GiB 的录制上限基础上，补项目级容量预估、配额和用户确认归档，避免多次采集挤满磁盘。',
            'P0：扩充非车辆资产 UV/材质能力清单和自动棋盘格对照，逐一处理实例化/样条及原材质恢复，不静默套用错误 UV。',
            'P1：完成 ThinkTwice 实际相机/历史/点云输入、控制输出和 CARLA 闭环；再完成 DriveAdapter 隔离依赖与权重构造；通过才解锁 UI。',
            'P1：完善预测时间契约、语义 BEV、统一事件定位和可复核评测指标，继续 ROS TF 与高分辨率展示验收。',
            'P1：拓展自然语言组合资产与复杂场景，但先做好依赖检查、明确确认及失败资产恢复。',
            'P2：完成当前代码/依赖/资产完整迁移包与第二台机器验证；获得明确许可后再推送 GitHub。',
        ], cases=cases)
    output = V / 'acceptance-report-20260914-manifest.json'
    with output.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    print(output)

if __name__ == '__main__':
    main()
