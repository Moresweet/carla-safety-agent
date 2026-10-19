# 编辑顺序核对

## 旧撤销绕过保护正式实测通过

生产空闲门禁通过，桥接重载为1406374；CARLA未重启。扩展实机回归在合成不确定日志存在期间尝试撤销另一条已确认记录：环境教堂槽和Audi A2车身槽都返回400，之后只读检查仍为目标纹理，显式恢复成功。两条正常历史/重复拒绝/恢复链路与清理均通过。

环境收据 `runs/validation/material-history-2b6d1cf539874bfc819715f91a498fd4/report.json`；车辆 `runs/validation/duplicate-texture-ef38b1fea0c84125a43c64bf1efb9d7b/report.json`。各自包含unresolved_old_undo_rejection，故障日志仍为明确标注的合成夹具。新建车辆和副本已删除、观察视角恢复，未删除用户对象。行人本次未重跑此新增分支；同槽保护不等于跨操作全局撤销完成。

## 旧历史撤销/重做不能绕过同槽故障保护

transition现于任何world verify和原生写入之前检查同槽未解决操作，覆盖环境材质和复用该方法的Actor材质。新增两种真实日志测试：先成功编辑，再产生另一条不确定操作，然后尝试撤销旧记录；必须拒绝且所有日志字节保持不变。相关52项通过（0.21秒）。该后续修改未部署，不将此前实机结果当作本分支验证。显式recover仍为专用处置入口；A→B→A分支和全局顺序仍未实现完整保护。

## 本轮完整回归

当前代码完整后端回归1808 passed in 58.33s；全部tools/test_*.mjs通过；前端五阶段生产构建退出0，vinext根路由Unknown静态分类提示仍在。覆盖最新材质同槽未解决保护及相关前端解析变更，不替代未完成的浏览器有效ID查询、全局撤销和真实崩溃恢复验收。

prepare_actor_history_browser.py亦已修正为先真实HTTP应用，再单独创建合成不确定日志，与原生回归工具保持一致，避免旧嵌套调用被新保护提前拒绝。这个准备工具改动尚未单独实跑，不把模块单测或其他工具成功当作该工具的实机证明。

## 车辆与行人恢复实景核对

已逐张打开以下四幅实际CARLA截图。行人恢复前裤装为青/紫校准格，恢复后为深色牛仔裤；上衣和鞋仍保留原外观。Audi A2恢复前为白色覆盖、后轮拱可见校准格，恢复后车身为原红色，轮胎/内饰仍可见。观察支持本次指定槽应用/恢复确有视觉效果，不代表整张UV逐像素对齐或所有相机角度都已检查。

![行人恢复前](../runs/validation/duplicate-texture-c4d1f0a6fad7429bb5a74c23fe292b8b/recovery-before.jpg)

![行人恢复后](../runs/validation/duplicate-texture-c4d1f0a6fad7429bb5a74c23fe292b8b/recovery-after.jpg)

![车辆恢复前](../runs/validation/duplicate-texture-f7ac6caa49ea41b8ad4920ddb1ca3430/recovery-before.jpg)

![车辆恢复后](../runs/validation/duplicate-texture-f7ac6caa49ea41b8ad4920ddb1ca3430/recovery-after.jpg)

## 行人和车辆实机历史/恢复/复制联合通过

正式桥接顺序执行regression_duplicate_texture.py的 --redo --material-history --material-recovery，分别覆盖walker.pedestrian.0001裤装槽和Audi A2车身槽。纹理应用、只读登记检查、撤销重做、过期revision拒绝、未解决槽新增编辑400拒绝、显式恢复、重复恢复拒绝、恢复后可重新应用均通过；带纹理复制及复制撤销/重做保留稳定身份与纹理引用，原对象记录未被改写。

故障部分已适配新保护：先实际HTTP应用，再创建合成不确定日志，测试后续处置，不声称真实事务中断。测试对象/副本均经正式删除接口清理，观察视角恢复。行人报告及截图：`runs/validation/duplicate-texture-c4d1f0a6fad7429bb5a74c23fe292b8b/`；车辆：`runs/validation/duplicate-texture-f7ac6caa49ea41b8ad4920ddb1ca3430/`。两份passed=true；本轮尚未逐张打开图片视觉核对。版本dirty警告仍在，其他Actor型号及全局撤销分支仍未覆盖。

## 检查失败保留具体原因

MaterialInspection非成功响应不再只显示HTTP状态码：对ok=false且error为字符串的JSON展示最多500字符原因，其余响应保留状态码。错误正文仍受既有15秒请求超时约束；React纯文本渲染，不注入HTML。Node测试覆盖具体原因、非JSON等效空值、错误结构、长说明截断，TypeScript通过。恢复回执的已有状态显示和禁止重复恢复逻辑未改变；新错误展示浏览器交互待验收。

## 新入口初步浏览器检查

正式localhost:3000展开项目面板及统一编辑历史，确认直达输入与类型选择显示、空输入选择按钮禁用。截图 `runs/validation/material-direct-lookup-empty-20260929.png` 已查看，发现输入边界不清楚，已改为纵向布局及显式边框/内边距。该截图为修正前；修正后视觉、输入有效ID和查询结果尚未完成验收，本轮没有触发恢复。

## 前端按操作ID直达检查

统一编辑历史新增精确32位材质operation_id输入和环境/Actor类型选择，选择后复用既有MaterialInspection与显式恢复流程，不依赖最新200条聚合列表。选择操作本身不发送修改请求；恢复进行中禁用切换。列表中同类型同ID项不重复渲染，避免出现两个恢复控件。TypeScript检查通过；尚未做浏览器交互和视觉验收，不宣称端到端功能已验收。

## 故障拒绝提示可定位

未解决同槽操作的拒绝信息现包含精确operation_id，并指向Editor History的检查/显式恢复流程；损坏日志则显示具体文件名，明确停止新增编辑而不删除历史。新增测试验证操作ID提示、损坏文件定位及拒绝时无修改，相关50项通过（0.20秒）。提示更新尚未重载正式桥接，尚未验证浏览器最终展示。

## 正式HTTP未解决槽拒绝与显式恢复通过

更新故障回归脚本：旧脚本在已有attempting日志的回调里再次HTTP申请同槽编辑，会被新保护正确拒绝，不能继续声称模拟了写后失败。新脚本先完成真实HTTP材质应用，再单独创建明确标注的合成不确定日志，以测试故障状态的下游处置；不称为真实事务中断或引擎崩溃。

实机执行 --concurrent --recovery 通过：未解决期间普通restore返回400，当前材质哈希及故障日志字节不变；inspection后显式恢复成功，原needs_attention/error仍保留；重复恢复被拒绝。最终原材质和观察视角恢复。证据 `runs/validation/material-history-f3ea7300dda144bbae85b752f6eb2a88/report.json`，同目录保存各阶段截图（本轮未逐张打开检查）。Actor故障实景、真实进程中断及全局撤销仍未验收。

## 正式部署与环境材质实机回归

部署前只读检查17条环境日志、20条Actor日志，全部可解析；环境有1条旧episode的未解决操作，Actor无未解决操作，没有删除或自动修复旧日志。生产空闲门禁通过后桥接重载为1388797，未重启CARLA。

正式执行regression_material_history.py --concurrent：教堂单槽两种纹理应用、并发撤销（一次成功、一次拒绝）、旧revision拒绝、重做及原材质恢复全部通过；观察视角恢复。报告和截图在 `runs/validation/material-history-4ec1583135464b098250d4ddef11df35/`。已打开检查restored.jpg。客户端/服务端dirty版本警告仍在。

这验证正常与并发撤销链路在新保护部署后可用；没有注入新的真实未解决操作，也未重新验证Actor实景，不能声称故障分支或全局撤销已全部验收。

## Actor材质使用同一未解决槽检查

抽取require_resolved_slot并由ActorMaterialHistory复用自身身份/日志校验器；apply_with_history在创建新日志和调用事务之前检查同槽旧操作。即使故障后的rollback返回，也不把原needs_attention日志视为已解决。新增测试确认新写入被拒绝且旧文件完全不变。环境材质、Actor材质、互斥及聚合历史49项通过（0.21秒）。

Actor函数的检查和写入依赖生产调用者已有的simulation_operation，不新增跨进程或独立调用者互斥保证。未部署、未做新的原生Actor纹理验收，全局编辑顺序仍未完成。

## 同槽未解决操作阻止新增编辑

MaterialHistory.execute在实例锁内、创建新日志或调用原生修改之前扫描已有材质日志。相同精确身份若存在attempting/needs_attention、pending撤销重做或未确认恢复，会拒绝新编辑，要求先检查并恢复；已明确confirmed的恢复允许继续。不同槽不因有效的其他槽故障被阻断。损坏或链接日志无法可靠识别目标时保守拒绝；扫描上限10000条，尚无索引优化。

新增真实日志测试覆盖失败后新编辑被拒绝、旧日志字节不变、没有新日志/原生修改、其他槽可编辑，以及显式恢复后再次编辑。材质与历史相关27项通过（0.18秒）。尚未部署正式桥接或实景验收；此保护仅针对环境材质MaterialHistory，不声称Actor材质、跨进程和全局撤销分支均已覆盖。

## 正式入口核对与回归保护

继续检查确认apply_material_slot、material_history_action、recover_material_history及Actor对应历史修改入口已使用simulation_operation。它持有同一仿真RLock，因此环境材质读取当前覆盖、execute以及原生修改在正式入口上已有外层互斥；上一轮模块实例锁修补不能据此解读为正式HTTP已证实存在覆盖竞态。

新增AST入口装饰器契约测试，以及执行实际material_history_callbacks的当前覆盖不匹配拒绝测试；连同已有真实线程仿真锁等待测试，3项通过（0.21秒）。当前材质不是历史预期source时，在纹理解码和原生写入前拒绝。这个值比较不能识别A→B→A的历史分支问题，仍不代表全局撤销顺序完成。

当前editor_history是多个独立日志的只读索引，明确不承诺全局撤销顺序。全局命令链、分支截断及跨操作失败补偿仍未实现完整验收，不能把按时间排序列表当成全局撤销栈。

本次发现并修复MaterialHistory.execute未使用实例历史锁的问题：transition、recover、inspect已经持锁，但新增编辑可与它们交错。execute现在以相同RLock覆盖日志准备、原生回调和结果落盘。真实线程测试持有该锁时调用execute，确认尚无原生回调和新日志目录；释放后编辑成功完成。材质历史、线程互斥、聚合历史共26项通过（0.17秒）。

范围：仅同一MaterialHistory实例；不是跨进程锁，不是多个历史类型之间的全局顺序，也不涵盖调用者在execute之前取得的世界快照。未重载正式桥接或新增实景编辑验收。下一步需要检查所有调用入口的身份/当前材质验证与写入是否同处受保护事务，再设计跨类型统一命令顺序。
