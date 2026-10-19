# 阶段 B 显示语义（第一轮）：几何、覆盖范围与云图色板

- 作者：Lead（Agent Teams 实施）
- 日期：2026-10-19
- 状态：第一轮已实现（代码 + 测试）；CoP 留待下一轮
- 上游依据：[五间隙电容单元设计](2026-10-19-capacitive-taxel-viewer-design.md)、[阶段 A 实现规格](2026-10-19-stage-a-implementation-spec.md)

## 0. 本轮顺序（按用户确认）

1. 核对真实受力面与间隙几何，区分实际间隙与显示内缩。
2. 以离散单元图为主视图；未直接测量的区域明确标识，不填零，不用平滑颜色暗示实测。
3. 再更换云图色板，注明"单元载荷插值示意"；**Mz 为零不代表没有接触**。
4. 最后加入"中心点模型下的离散 CoP"（本轮未做）。

## 1. 几何语义（已实现）

事实：标称硬件 pitch == taxel_width == 10 mm，阵列无物理间隙（见 [CHANGE_NOTICE_2026-09-22.md](../../../CHANGE_NOTICE_2026-09-22.md)）。界面上的格间空白来自渲染内缩 GAP_RENDER_SCALE = 0.88（每轴 12%），仅用于把相连单元区分成离散格子。

落地：阵列窗口常驻说明栏 field_note，离散视图文案逐字为

> 离散单元视图：每格是一个单元的受力面。标称 pitch = 单元宽度（无物理间隙）；格间空白是渲染分隔（内缩 12%），不是实物缝隙。

内缩百分比由 GAP_RENDER_SCALE 推导（DISPLAY_INSET_PERCENT），改常量即改文案，不会出现"代码内缩与文案不符"。模型几何（.rect()、命中测试、聚合律）一律不变。

## 2. 离散主视图与覆盖范围（已实现）

- 默认视图仍是离散单元视图；云图是次级显示，不改变"每格一个受力面"的主语义。
- 云图模式新增 cloud_sample_markers：在全部单元中心画固定像素十字，**明确标出真实采样位置**；切回离散视图即隐藏。
- 云图常驻注记：

> 单元载荷插值示意：颜色由单元采样点插值得到，未直接测量的区域是插值结果而非实测；十字标记为真实采样位置。

- 云图标题不再写 display interpolation only，改为 cell-load interpolation schematic（中文注记在说明栏，避免长标题撑宽视图）。
- 不填零：插值沿用 cloud_field.interpolate_field 的归一化加权平均；零贡献区域为 NaN（透明），未引入任何"缺失即 0"的填充。
- 力矩通道附注：

> 力矩为各单元力对阵列中心的聚合；该通道为零不代表没有接触。

## 3. 云图色板（已实现，方案 2）

- 色板定义在 ui_theme.py（CLOUD_SEQUENTIAL_LUT、CLOUD_DIVERGING_LUT），pyqt_live._cloud_lut() 是唯一取用点，**云图像素与色条共用同一份 stops/colours**，不存在"图亮条暗"。
- cloud_field.py 的 SEQUENTIAL_LUT / DIVERGING_LUT **一行未改**（test_cloud_field.py:91-110 锁定其 RGB）。
- 发散色板零点由纯白改为深石板 (30, 41, 59)：零力矩不再白屏；负向青蓝、正向橙红，暗背景可读。
- 顺序色板零点贴近画布底色 (15, 23, 42)，峰值红 (239, 68, 68)，中间蓝→青→琥珀。
- 未采用"降低云图不透明度"的做法：会同时削弱有效信号，且画布与色条对不上。

## 4. 尚未实现：离散 CoP（下一轮）

前置条件已满足（覆盖范围与云图含义已说清）。实现时必须保留：

- 仅在**多单元阵列**且法向载荷有效时显示；单一单元不能定位其受力面内接触点。
- 标签写"中心点模型下的离散 CoP"，不称 ZMP、不称接触面积、不承诺滚动识别。
- 无效/零载/符号混合帧隐藏，尾迹在无效帧处断开；不取绝对值、不裁零掩盖。
- 尾迹按样本真实时间截取，不以"固定帧数 = 固定秒数"实现。
- CoP 由**原始离散读数**计算，不能反过来对云图积分。

## 5. 验证

```text
QT_QPA_PLATFORM=offscreen conda run -n taxel-pyqt python -m unittest \
  test_cloud_field test_pyqt_live test_pyqt_single_taxel test_review_regressions \
  test_ui_theme test_sensor_structure_items
Ran 105 tests ... OK
```

新增断言：

- test_geometry_note_separates_display_inset_from_physical_gap
- test_cloud_note_explains_interpolation_and_moment_zero
- test_cloud_view_marks_every_sample_position
- test_cloud_uses_the_theme_palette_and_bar_follows_it
- test_cloud_image_uses_the_same_palette_as_the_bar
- test_cloud_palettes_are_dark_friendly_and_monotonic

边界：本轮为 offscreen 渲染核对（手动加载系统字体），未在桌面字体下验收；不动模型/历史/数据源/依赖。
