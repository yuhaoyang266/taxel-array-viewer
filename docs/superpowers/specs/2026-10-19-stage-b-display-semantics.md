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

**不能把"无物理间隙"当作已确认事实。** 需要分别描述三个量：

- **本体外轮廓**：整个传感器占用多大空间。
- **白色受力面**：实际接触、向活动板传力的区域。
- **单元中心距（pitch）**：相邻传感器的位置关系。

即使本体紧挨着，白色受力面之间仍可能隔着固定框架；本体之间还可能另有装配间隙。当前 10 mm × 10 mm 与 3 × 3 只是标称演示配置，不能据此推导真实覆盖区。

落地：阵列窗口常驻说明栏 field_note，离散视图文案逐字为

> 几何为标称演示配置，实际受力面及间隙范围尚未确认。十字表示单元合力的等效位置；云图仅为块级载荷趋势插值。格间空白仅为显示分隔（渲染内缩 12%），不代表本体或受力面之间的实际间隙。

单元窗口结构详情另有常驻行 structure_geometry_note：

> 本体外轮廓、白色受力面、单元中心距是三个独立量：本体相邻不代表受力面相邻，受力面之间可能有固定框架，本体之间也可能有装配间隙。本图为标称演示配置，实际尺寸与间隙尚未确认。

内缩百分比仍由 GAP_RENDER_SCALE 推导（DISPLAY_INSET_PERCENT），但文案把它限定为显示参数。**在阵列布置与受力面尺寸确认前，不生成任何"真实测量覆盖区"**：当前以离散单元合力图为主视图，云图只作为块级载荷趋势插值。模型几何（.rect()、命中测试、聚合律）一律不变。

## 2. 离散主视图与覆盖范围（已实现）

- 默认视图仍是离散单元视图；云图是次级显示，不改变"每格一个受力面"的主语义。
- 云图模式新增 cell_resultant_markers：在全部单元中心画固定像素十字，表示**该单元合力的等效位置（中心点模型）**；它不是采样点，也不是受力面内的接触点。切回离散视图即隐藏。
- 云图常驻注记：

> 云图仅为块级载荷趋势插值，不代表实测连续场；十字表示单元合力的等效位置（中心点模型），不是受力面内的接触点。

- 云图标题不再写 display interpolation only，改为 block-level cell-load trend interpolation（中文注记在说明栏，避免长标题撑宽视图）。
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
Ran 107 tests ... OK
```

新增断言：

- test_geometry_note_states_the_uncertainty_instead_of_claiming_a_gap
- test_cloud_note_explains_block_trend_and_equivalent_position
- test_cloud_view_marks_every_cell_resultant_position
- test_structure_panel_states_geometry_uncertainty
- test_note_separates_envelope_face_and_pitch
- test_cloud_uses_the_theme_palette_and_bar_follows_it
- test_cloud_image_uses_the_same_palette_as_the_bar
- test_cloud_palettes_are_dark_friendly_and_monotonic

边界：本轮为 offscreen 渲染核对（手动加载系统字体），未在桌面字体下验收；不动模型/历史/数据源/依赖。
