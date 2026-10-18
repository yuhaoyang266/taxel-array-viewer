# 更改说明：触觉阵列几何与力学约定对齐（2026-09-22）

> 用途：与 pureshear 侧（传感器/采集方）协调对齐。
> 发出方：taxel-array-viewer（可视化前端）。设计依据：本仓库 `DESIGN.md`
> 末节 "Hardware geometry alignment (2026-09-22)"；接口契约详见 `INTEGRATION.md`。

## 1. 变更背景（Owner 提供的硬件事实）

真实传感器为**阵列电容式三维力传感器**：

- 单个 taxel 约 **10 mm × 10 mm**（标称值，"大概 10mm"，非计量记录）；
- 阵列**无间距**：相邻 taxel 中心距 = taxel 边长 = 10 mm（pitch == width）；
- 力学约定：每个 taxel 的三轴力按**作用于该 taxel 中心点的集中力**处理，
  不解析 taxel 内部接触位置，不建模分布载荷，无局部扭矩测量。

## 2. 本侧已批准的变更（taxel-array-viewer）

| 项 | 变更前 | 变更后 |
| --- | --- | --- |
| 默认几何 | 20 mm 演示假设（明确"非硬件声明"） | 10 mm 硬件标称值，pitch == width，两轴同 |
| 涉及入口 | — | `model.py`、`app.py`、`pyqt_live.py`、`rerun_live.py`、`pyqt_single_taxel.py` 的默认值 |
| 力学/聚合律 | F = Σfᵢ，M = Σ(rᵢ − r₀) × fᵢ | **不变**（rᵢ 本来就是 taxel 中心） |
| 数据契约 | (rows, cols, 3) float64 `[fx, fy, fz]`，单位 N | **不变** |
| 渲染/校验 | 88% 内缩（pitch==width 时）、width ≤ pitch 校验 | 保留，在 10/10 默认下仍生效 |
| 云图插值 | 纯显示用途，sigma = 0.55 × pitch | 不变，随新 pitch 自动缩放 |

**状态**：设计已批准并记录；代码默认值变更正在走 Builder → review（→ redtest）
流程，尚未合入。本说明发出时不代表代码已切换。

## 3. 需要 pureshear 侧对齐的事项

1. **帧格式**：每帧 `(rows, cols, 3)` float64，`[fx, fy, fz]`，**标定后的牛顿值**，
   必须有限（无 NaN/inf 混入有效数据；无效元件的标记方式见第 4 节问题）。
2. **几何配置**（启动时一次性给定）：`rows, cols, pitch_x_mm, pitch_y_mm,
   taxel_width_x_mm, taxel_width_y_mm, hz`。本侧默认 10/10/10/10，
   请确认实物一致或提供精确值。
3. **坐标约定**：+x 屏幕向右（列方向）、+y 屏幕向上（行方向）、+z 出传感器面
   （法向）；力 N，力矩 N·m 绕阵列几何中心右手系。**安装有旋转的元件，其局部
   fx/fy 须在 pureshear 侧先旋到阵列坐标系**再发出。
4. **元件 → (row, col) 映射表**及安装朝向说明。
5. **标定边界**：原始电容 counts 不进前端；C→F 反演在 pureshear 侧完成，
   仅在标定有效域内取值，不外推。
6. **力学接口一致性**：pureshear 每元件只上报三轴力、不上报局部扭矩；
   力作用点按元件中心处理——与本侧聚合律前提一致，请确认无冲突。

## 4. 待 pureshear 回复的开放问题

1. 实际阵列规模 rows × cols？（本侧 3×3 目前仅为演示默认）
2. pitch 精确值与公差？（10.0 mm 为标称"大概"值）
3. fx/fy/fz 符号约定是否与本侧第 3.3 条一致？
4. 标称采样率 hz？
5. 无效 / 离面 / 超量程元件如何标记（NaN？独立有效位？）

## 5. 明确不在本次变更范围

- 传输机制不变（UDP 实时帧 / `.npz` 文件重放均沿用 `INTEGRATION.md` 第 5 节）。
- 云图插值仍为纯显示，不构成物理 traction 场重建。
- ShearCue 仿真侧 `TaxelArrayConfig`（pitch 10 / width 8 mm）与"无间距"的矛盾
  另行立项处理，不在本说明范围。
- 不涉及真机操作、标定实验或通信协议变更。
