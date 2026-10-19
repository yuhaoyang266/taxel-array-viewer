# 阶段 A 实现规格：暗色仪器主题、五间隙结构图元、双入口接线与测试变更

- 作者：stage-a-code-spec（Agent Teams 阶段 A 实现规格）
- 日期：2026-10-19
- 状态：docs only。本轮不修改任何产品 .py，不运行 GUI/测试/硬件，不宣称任何回归通过。
- 上游权威设计：[五间隙电容单元：前端适配设计与改造计划](2026-10-19-capacitive-taxel-viewer-design.md)。本文件是其 §5/§6/§7 阶段 A 的可执行展开，不改变设计结论。
- 代码审查基线：2e39c10（git rev-parse HEAD 已核对）。**文中全部行号按该基线逐文件读取源码核对**，核对差异见附录 A。
- 实现轮运行环境：conda 隔离环境 taxel-pyqt（README 第 137–138 行）。

---

## 0. 硬约束

1. 只改显示层：新增 ui_theme.py、sensor_structure_items.py；修改 pyqt_live.py、pyqt_single_taxel.py 及测试。**不得改** model.py、live_history.py、live_source.py、cloud_field.py、app.py、tri_axis_array/**、requirements-*.txt。
2. 数据契约不变：readings 形状 (rows, cols, 3)、单位 N、力矩 N·m、阵列几何中心 + 中心点模型。
3. 几何默认不变：3×3、pitch 10 mm、width 10 mm（model.py:35–40）。
4. 结构图元一律"非比例示意"：界面与场景文本中不得出现任何 mm/µm/μm/pF/N 的间隙、厚度、位移数值；唯一允许的数字是件数 ×4、×1。
5. 不在阵列单元上画五间隙/电容：GAP_RENDER_SCALE = 0.88（pyqt_live.py:56）继续只表示渲染分隔（设计文档第 138 行）。
6. 不把未测量状态画成测量结果：不加载荷-位移动画、不标 pF/位移、不新增健康/滑移/OOR 状态。
7. 本轮不运行任何东西；实现轮按实际输出报告。

交付物：ui_theme.py、sensor_structure_items.py（新增）；pyqt_live.py、pyqt_single_taxel.py（修改）；test_ui_theme.py、test_sensor_structure_items.py（新增）；test_pyqt_live.py、test_pyqt_single_taxel.py（修改）；README.md 第 138 行测试命令追加新模块（实现 PR 内）。

建议实现顺序：①ui_theme + 测试 ②结构图元 + 测试（不接线）③pyqt_live 接线 + 测试改动 ④pyqt_single_taxel 结构面板 + 测试 ⑤README 与全量回归。

---

## 1. ui_theme.py 规格

### 1.1 模块定位与导入约束

- 只放显示常量与纯显示助手；不含力学/几何/历史逻辑。
- **不得 import pyqtgraph**（避免 PYQTGRAPH_QT_LIB 顺序问题；两个 GUI 模块在 import 前已设置该变量），**不得 import cloud_field**。
- 可 import PySide6.QtCore/QtGui/QtWidgets；不创建 QApplication。
- 令牌为模块级常量（测试无需窗口即可断言）。

### 1.2 令牌表（权威值）

设计文档第 165 行给定三个界面底色，本规格以此为准：

| 令牌 | 值 | 用途 |
|---|---|---|
| WINDOW_BG | #0B0F17 | 主窗口背景 |
| PANEL_BG | #111827 | 面板/右侧绘图区背景 |
| CANVAS_BG | #0D131F | 力场画布、结构视图画布 |
| BORDER | #243244 | 面板/按钮描边 |
| TEXT_PRIMARY | #E5E7EB | 主要文本、数字读数 |
| TEXT_MUTED | #94A3B8 | 图例次要文本、单位、注记 |
| ZERO_LINE_COLOUR | #4B5563 | 曲线零位参考线（虚线） |
| AXIS_COLOURS | {"Fx": (239,83,80), "Fy": (102,187,106), "Fz": (66,165,245)} | 与现有 FORCE_COLOURS 同值 |
| MOMENT_COLOURS | {"Mx": (38,198,218), "My": (255,202,40), "Mz": (171,71,188)} | 与 pyqt_live.py:39–43 同值 |
| ARROW_LINE_COLOUR | (203,213,225) | 箭头杆（原 (30,30,30)，pyqt_live.py:353） |
| ARROW_COLOUR | (231,236,245) | 箭头头部（原 (20,20,20)，pyqt_live.py:360–361、pyqt_single_taxel.py:244–245） |
| SELECTION_COLOUR | (255,215,0) | 选中轮廓，保持金色 |
| TAXEL_PEN | (12,18,28) | 阵列单元描边（原 (40,40,40)，pyqt_live.py:52） |
| CLOUD_TAXEL_PEN | (100,116,139) | 云图网格描边（原 (150,150,150)，pyqt_live.py:53） |

结构部件身份色（设计文档第 168 行：黄色/白色只表示部件身份，不随载荷染色）：

| 令牌 | 值 | 用途 |
|---|---|---|
| FRAME_FILL / FRAME_PEN | #1B2534 / #3F4C5F | 固定外框、基座 |
| FIXED_ELECTRODE_FILL / _PEN | #8FA3B8 / #C7D2DE | 固定电极（四侧+底部） |
| MOVING_PLATE_FILL / _PEN | #F2C744 / #B9880E | 中央黄色活动板 |
| FORCE_FACE_FILL / _PEN | #F8FAFC / #CBD5E1 | 白色受力面 |
| SILICONE_FILL / _PEN | #1F6F6B / #3DD6C4 | 硅胶支撑（示意填充+斜线） |
| GAP_ACCENT | #22D3EE | 仅表示"这里有间隙"的示意标记，不得附数值 |
| LEADER_COLOUR | #7C8BA1 | 引线、注记线 |

字体：MONO_FAMILIES = ("JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "monospace")，MONO_POINT_SIZE = 10。等宽字体只用于数字读数标签（pyqt_live.py:188–191 selected_label、pyqt_single_taxel.py:181–183 info_label）、图例文本、结构视图文本；**不通过窗口 QSS 全局设置 font-family**（见 §6 R1/R10）。

### 1.3 公共 API

`python
def qcolor(value) -> QtGui.QColor            # 接受 QColor / (r,g,b) / "#RRGGBB"
def with_alpha(value, alpha: int) -> QtGui.QColor
def mono_font(point_size: int = MONO_POINT_SIZE, bold: bool = False) -> QtGui.QFont
def mono_family_qss() -> str                 # 带 monospace 兜底的字体族串
def window_qss() -> str                      # 仅颜色；禁止布局度量
def label_qss(role: str = "primary") -> str  # "primary" | "muted" | "mono"
def panel_qss() -> str
def legend_qss() -> str
def toggle_qss() -> str                      # 唯一允许小 padding，仅用于单元窗口
def apply_window_theme(window) -> None       # window.setStyleSheet(window_qss())
def apply_panel_theme(widget) -> None        # widget.setStyleSheet(panel_qss())
def apply_canvas_theme(widget, role="canvas") -> None
    # role=="canvas" -> CANVAS_BG；role=="panel" -> PANEL_BG
    # 优先 widget.setBackground(qcolor)（pyqtgraph GraphicsView/PlotWidget/GraphicsLayoutWidget 有此 API，
    # 见附录 A：GraphicsView.py:124），否则退回 widget.setBackgroundBrush(QtGui.QBrush(...))，
    # 因此 ui_theme 无需 import pyqtgraph。
def field_ramp_colour(normalised: float) -> tuple[int, int, int]
`

field_ramp_colour 必须与现有两处实现**数学等价**（pyqt_live.py:600–614、pyqt_single_taxel.py:304–320）：

`python
def field_ramp_colour(normalised):
    n = 0.0 if normalised < 0.0 else (1.0 if normalised > 1.0 else float(normalised))
    if n <= 0.45:
        f = n / 0.45
        return (round(25 + f * 55), round(55 + f * 125), round(150 + f * 85))
    f = (n - 0.45) / 0.55
    return (round(80 + f * 165), round(180 - f * 105), round(235 - f * 180))
`

端点必须精确：0.0 → (25,55,150)；0.45 → (80,180,235)；1.0 → (245,75,55)。

### 1.4 QSS 片段与硬约束

window_qss() 只含颜色，**不得**包含 padding / margin / min-width / max-width / font-size / font-family：

`css
QMainWindow { background: #0B0F17; }
QMainWindow > QWidget { background: #0B0F17; }
QLabel { color: #E5E7EB; }
QPushButton, QToolButton { color: #E5E7EB; background: #111827; border: 1px solid #243244; }
QPushButton:checked, QToolButton:checked { background: #1E2A3A; }
`

panel_qss()："QWidget#StructurePanel { background: #111827; border: 1px solid #243244; border-radius: 6px; }"

apply_window_theme 只在窗口构造里调 window.setStyleSheet(...)（窗口局部）；**禁止** QApplication.setStyleSheet（GUI 测试直接构造窗口，全局样式会跨用例泄漏并可能抬高 minimumSizeHint）。唯一允许 padding 的 toggle_qss()（padding: 2px 8px）只用于 pyqt_single_taxel（该窗口无 800 px 断言）。

### 1.5 与 cloud_field.py 既有 LUT 的共存（硬规则）

事实（已核对）：cloud_field.py:24–34 SEQUENTIAL_LUT、:35–45 DIVERGING_LUT；test_cloud_field.py:91–110 **锁定** DIVERGING_LUT（白中点 ≥250、NaN→alpha 0、上端 (214,39,40)、下端 (31,119,180)）；test_pyqt_live.py:437–451 要求色条渐变逐 stop 等于 window._cloud_lut()（pyqt_live.py:517–520）的整数色；test_pyqt_live.py:291–353 锁定力矩/剪切色条量程语义。

因此：

1. cloud_field.py 是云图色板唯一来源，**本阶段一行不改**；不得为暗背景"调暗端点"。
2. ui_theme.py 不定义、不包装、不引用云图 LUT，只负责底色/文本/部件身份色/语义通道色。
3. 暗背景 + 白中点的处理只通过**画布背景色**（apply_canvas_theme）实现，不改像素；若需降低亮度可后续对 cloud_image 用 setOpacity（不改 image 数组、不影响上述测试），本阶段不做。
4. pyqt_live._cloud_lut()（517–520）与 _cloud_pg_colour_map()（533–541）保持原样。
5. 语义通道色（Fx/Fy/Fz 曲线/箭头）与云图标量色板是两套；本规格只统一前者。

### 1.6 接线点（逐行）

| 文件:行 | 现状 | 动作 |
|---|---|---|
| pyqt_live.py:34–38 | FORCE_COLOURS 字面量 | 改为 dict(ui_theme.AXIS_COLOURS)，键名不变 |
| pyqt_live.py:39–43 | MOMENT_COLOURS 字面量 | dict(ui_theme.MOMENT_COLOURS) |
| pyqt_live.py:52–53 | TAXEL_PEN / CLOUD_TAXEL_PEN | 取主题值 |
| pyqt_live.py:184 | resize(1450, 850) | 其后 apply_window_theme(self) |
| pyqt_live.py:190 | selected_label 的 font-size:15px; padding:4px | 改 label_qss() + padding 仍 4px，并 setFont(mono_font(10))；第 189 行 setWordWrap(True) 不动 |
| pyqt_live.py:196–199 | field_plot / right_plots | 其后 apply_canvas_theme(field_plot,"canvas")、apply_canvas_theme(right_plots,"panel") |
| pyqt_live.py:272 / :384 | addLegend(offset=...) | 追加 labelTextColor、labelTextSize（pyqtgraph 0.14 支持，附录 A） |
| pyqt_single_taxel.py:17–21 | FORCE_COLOURS 小写键 | 由 AXIS_COLOURS 派生小写键 |
| pyqt_single_taxel.py:176 | resize(1200, 680) | 其后 apply_window_theme(self) |
| pyqt_single_taxel.py:182 | info_label 样式（font-size:15px; bold; padding:6px） | 去掉 font-size，保留 padding 6px + bold + TEXT_PRIMARY；setFont(mono_font(10, bold=True))；可加 setWordWrap(True)（该窗口无几何断言） |
| pyqt_single_taxel.py:188–192 | sensor_plot / force_plot | apply_canvas_theme(sensor_plot,"canvas")、apply_canvas_theme(force_plot,"panel") |
| pyqt_single_taxel.py:272 / :278 | 图例 / 曲线笔色 | 图例同上；笔色取 AXIS_COLOURS 小写键 |
| pyqt_single_taxel.py:218–219 | taxel_item 笔/刷 | 笔 TAXEL_PEN；刷 field_ramp_colour(0.0) |
| pyqt_single_taxel.py:232 / :244–245 | 箭头杆/头部颜色 | ARROW_LINE_COLOUR / ARROW_COLOUR，宽度与几何参数不动 |
| pyqt_single_taxel.py:260 | 选中轮廓金色 | SELECTION_COLOUR |
| pyqt_single_taxel.py:307–320 | 内联斜坡 | 改调 field_ramp_colour（等价） |

禁止项：全局 QApplication.setStyleSheet / 全局 pg.setConfigOption("background")；QSS 中新增布局度量；改 pg.setConfigOptions（pyqt_live.py:182、pyqt_single_taxel.py:174）；替换或包装云图 LUT；改 FORCE_COLOURS 键大小写（pyqt_live 用 "Fx"/"Fy"/"Fz"，pyqt_single_taxel 用 "fx"/"fy"/"fz"）。

---

## 2. sensor_structure_items.py 规格

### 2.1 模块约定

- 只画静态、示意、非尺寸结构图与阵列受力面装饰；无数据输入、无动画、无载荷响应。
- 内部单位：1.0 场景单位 = 1.0 示意 mm；整体由 StructureMetrics.from_diameter(diameter_mm) 按标称单元宽度缩放，所有几何量都是该宽度的**分数**。
- 模块 docstring 必须写明：所有尺寸均为示意比例，不含任何真实间隙/厚度/位移数值，界面也不得显示。
- 场景文本不得出现数字尺寸，只允许件数 ×4 / ×1；由 dimension_texts() 供测试强制。

### 2.2 StructureMetrics（全部为 span 的分数，span = diameter_mm）

| 字段 | 值 | 含义 |
|---|---|---|
| frame_outer / frame_ring / frame_radius | 1.30 / 0.14 / 0.10 × span | 固定外框外宽、环厚、圆角 |
| plate_diameter | 0.66 × span | 活动板直径（半径 0.33） |
| face_diameter | 0.46 × span | 白色受力面直径（半径 0.23，小于板） |
| gap | 0.05 × span | **示意间隙常数**（五间隙共用；非实物间隙） |
| lateral_pad_inner / outer / width | 0.38 / 0.51 / 0.24 × span | 俯视四侧固定电极（内缘 = 板半径+gap；外缘 = 外框环内缘） |
| hidden_bottom_radius | 0.30 × span | 俯视"板下底部电容"虚线隐藏轮廓半径 |
| base_half / base_top / base_bottom | 0.65 / -0.36 / -0.50 × span | 剖面基座 |
| bottom_electrode_half / bottom_electrode_top | 0.30 / -0.30 × span | 剖面底部电极 |
| plate_bottom / plate_top | -0.25 / -0.01 × span | 活动板（plate_bottom − 电极上表面 = gap） |
| face_top | +0.12 × span | 受力面上缘 |
| side_wall_inner / outer | 0.44 / 0.51 × span | 剖面侧壁 |
| lateral_electrode_inner / top | 0.38 / +0.02 × span | 侧向电极（0.38 − 0.33 = gap） |
| silicone_inner / outer | 0.10 / 0.30 × span | 硅胶支撑径向范围 |

几何自检（测试可断言）：plate_bottom − bottom_electrode_top == gap；lateral_electrode_inner − plate_diameter/2 == gap；lateral_pad_inner − plate_diameter/2 == gap；lateral_pad_outer == frame_outer/2 − frame_ring。

### 2.3 坐标映射：局部示意 mm → QGraphics 场景

- 每个图元以自身原点为中心，场景 = 图元局部坐标；缩放交给 StructureView.fitInView，不手工 scale。
- Qt 场景 y 向下、示意图 y 向上；**统一经两个助手映射，禁止散落写 -y**：

`python
def scene_point(x_mm, y_mm) -> QtCore.QPointF:          # 唯一允许的 y 翻转点
    return QtCore.QPointF(float(x_mm), -float(y_mm))
def scene_rect(centre_x_mm, centre_y_mm, width_mm, height_mm) -> QtCore.QRectF: ...
`

- 文本不做翻转：QGraphicsSimpleTextItem 用 scene_point 定位，并设 ItemIgnoresTransformations（恒定像素字号）。不得对 StructureView 或根图元做 scale(1, -1)（会把文字镜像）。
- 文本放在 label_band = 0.24 × span 的几何外左右带内，用 LEADER_COLOUR 引线指向部件；允许 ±10% 微调避让，但不得把标签移进几何内部、不得省略图例项。

### 2.4 图元层级与 zValue（模块常量）

| 常量 | 值 | 用途 |
|---|---|---|
| Z_FRAME | 1.0 | 固定外框 / 基座 / 侧壁 |
| Z_ELECTRODE | 2.0 | 固定电极 |
| Z_SILICONE | 3.0 | 硅胶（半透明+斜线） |
| Z_GAP | 4.0 | 间隙标记（双线/虚线/隐藏轮廓） |
| Z_PLATE | 5.0 | 中央活动板 |
| Z_FACE | 6.0 | 白色受力面 |
| Z_LEADER | 7.0 | 引线 |
| Z_TEXT | 8.0 | 场景文本 |

结构图元 z 带固定 1..8；pyqt_live 力场已有 cloud_image=-1、arrow_lines=10、arrow_heads=11、selection_outline=20（pyqt_live.py:363–364, 371, 338），二者不同 scene，不得为"统一"改动既有 z。

### 2.5 TopViewStructureItem（俯视）

1. 固定外框环：QGraphicsPathItem，外圆角矩形 − 内圆角矩形（OddEvenFill），FRAME_*，z=Z_FRAME（本体固定结构，设计文档第 148 行）。
2. 四侧固定电极：0°/90°/180°/270°（右/上/左/下）各一圆角矩形，径向 lateral_pad_inner..outer、切向宽 lateral_pad_width，FIXED_ELECTRODE_*，z=Z_ELECTRODE。
3. **四个侧向间隙标记**：每处电极内缘与板外缘之间画两条平行短线（GAP_ACCENT，cosmetic 1.2 px）+ 端封口；z=Z_GAP；保存 self.lateral_gap_markers（长度必须 4）。
4. 中央活动板：**方形**圆角矩形，边长 plate_diameter，MOVING_PLATE_*，z=Z_PLATE。本体确认的黄色活动板是方形；只有其上覆的白色受力面是圆形（圆柱截面）。方形板的四条平边才是四侧间隙的基准，圆形板会让间隙线与弧边错位。
5. 白色受力面：QGraphicsEllipseItem，直径 face_diameter，FORCE_FACE_*，z=Z_FACE。受力面小于活动板（与"扩大目标暂限于中央黄色板上表面"一致，设计文档第 39 行），为将来扩大留空间。
6. **底部电容隐藏轮廓**：半径 hidden_bottom_radius 的虚线圆（GAP_ACCENT），z=Z_GAP，保存 self.bottom_cap_hidden_marker，配标签"底部电容 ×1（板下，见剖面）"——这是俯视不让人误以为只有四路的关键（设计文档第 42 行）。
7. 场景文本（z=Z_TEXT，ItemIgnoresTransformations）："固定外框"、"中央活动板"、"受力面"、"侧向电容 ×4"、"底部电容 ×1（板下）"、"结构示意，非尺寸图"；引线 z=Z_LEADER。

### 2.6 CrossSectionItem（剖面）

1. 固定基座：圆角矩形 base_bottom..base_top × 1.30 span 宽，FRAME_*，z=Z_FRAME。
2. 两侧壁：x ∈ [side_wall_inner, side_wall_outer]（左右镜像），y ∈ [base_top, lateral_electrode_top]，FRAME_*，z=Z_FRAME。
3. 底部固定电极：x ∈ ±bottom_electrode_half，y ∈ [base_top, bottom_electrode_top]，FIXED_ELECTRODE_*，z=Z_ELECTRODE。
4. **底部间隙标记（唯一）**：y=bottom_electrode_top 与 y=plate_bottom 两条水平线 + 端封口（GAP_ACCENT），z=Z_GAP，保存 self.bottom_gap_marker。
5. 左右侧向电极：x ∈ [lateral_electrode_inner, side_wall_inner]，y ∈ [-0.22 span, lateral_electrode_top]，FIXED_ELECTRODE_*，z=Z_ELECTRODE。
6. **左右侧向间隙标记（2 个）**：板外缘与电极面之间的竖线 + 端封口，GAP_ACCENT，z=Z_GAP，保存 self.lateral_gap_markers（长度 2）。
7. 硅胶支撑（2 处）：板下、底部电极两侧的微梯形（silicone_inner..outer，y ∈ [base_top, plate_bottom]，外宽内窄），SILICONE_FILL 半透明 + SILICONE_PEN 斜线纹理，z=Z_SILICONE；文字只写"硅胶支撑（示意）"，不声称实际分布/刚度（设计文档第 43、147 行）。
8. 中央活动板：圆角矩形 x ∈ ±plate_diameter/2，y ∈ [plate_bottom, plate_top]，MOVING_PLATE_*，z=Z_PLATE。
9. 白色受力面：圆角矩形 x ∈ ±face_diameter/2，y ∈ [plate_top, face_top]，FORCE_FACE_*，z=Z_FACE（受力面坐在板上表面 → 三层身份可辨：外框固定 / 黄板活动 / 白面传力）。
10. 场景文本："受力面"、"中央活动板"、"底部电容 ×1"、"侧向电容（左右）"、"前后两侧见俯视"、"硅胶支撑（示意）"、"结构示意，非尺寸图"。

**不得**画：位移箭头、受力方向箭头、尺寸标注、mm/µm/pF 数值、变形后轮廓（设计文档第 74、150 行）。

### 2.7 五个间隙怎么读（验收要点）

| 间隙 | 俯视图 | 剖面图 |
|---|---|---|
| 右 / 左 / 上 / 下侧向 | 各 1 个双线标记（共 4） | 左右各 1 个竖双线（2 之一），其余注记"前后两侧见俯视" |
| 底部 | 1 个虚线隐藏轮廓 + "板下，见剖面" | **1 个**水平双线标记 |

模块常量 LATERAL_GAP_COUNT = 4、BOTTOM_GAP_COUNT = 1 作为唯一计数来源；两视图都不显示数值。

### 2.8 文案常量（逐字，测试断言）

`python
SCHEMATIC_NOTE = "结构示意，非尺寸图；当前仅显示三轴力，未接入间隙/电容读数"
TOP_VIEW_CAPTION = "俯视示意：固定外框 + 中央活动板 + 四侧电容（间隙为示意，非尺寸）"
SECTION_CAPTION = "剖面示意：底部电容 + 侧向电容；硅胶位置仅示意"
IN_SCENE_NOTE = "结构示意，非尺寸图"
LEGEND_ITEMS = (
    ("固定外框 / 固定电极", "本体固定结构", FRAME_PEN),
    ("中央活动板", "随受力运动的部件", MOVING_PLATE_FILL),
    ("白色受力面", "接触传力面", FORCE_FACE_FILL),
    ("侧向电容 ×4", "电容间隙，示意", GAP_ACCENT),
    ("底部电容 ×1", "电容间隙，示意", GAP_ACCENT),
    ("硅胶支撑", "弹性复位，位置示意", SILICONE_PEN),
)
LEGEND_NOTE = "黄色=活动部件，白色=传力面，青色=示意间隙；间隙不作尺寸标注。"
`

SCHEMATIC_NOTE 必须与设计文档第 151 行逐字一致（常驻注记）。图例由 StructureLegendWidget（QWidget：色块 + 两列文本）展示 LEGEND_ITEMS 与 LEGEND_NOTE；颜色与文字必须成对出现，不能只靠颜色识别（设计文档第 165–166 行）。

### 2.9 点击安全（关键）

事实（pyqtgraph 0.14.0 源码，附录 A）：GraphicsScene.mousePressEvent 只有 mouseGrabberItem() is None 时才登记 clickEvents；图元在按下时抢到抓取，sigMouseClicked 不发出，pyqt_live._on_field_click（pyqt_live.py:394–402）失效。ViewBox 无 mousePressEvent、mouseClickEvent 只处理右键菜单，故现状点击可用，新图元必须不改变这一点。

强制规则：

1. 每个图元（含子项）setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)。
2. 不设 ItemIsSelectable / ItemIsMovable / ItemIsFocusable。
3. 不实现 mousePressEvent / mouseReleaseEvent / mouseMoveEvent / mouseDragEvent，不 grabMouse、不 setCursor、不开 acceptHoverEvents。
4. 结构视图是独立 widget，不叠在 sensor_plot / field_plot 之上；StructureView 另设 setInteractive(False) 与 WA_TransparentForMouseEvents。
5. 阵列受力面图元（TaxelFaceRectItem / TaxelFaceEllipseItem）只重写 paint()，不重写 boundingRect()/shape()/mousePressEvent()；点击仍由 geometry.locate_taxel(...)（pyqt_live.py:400）在 view 坐标完成。

### 2.10 公共 API 与测试钩子

`python
# 常量：SCHEMATIC_NOTE / TOP_VIEW_CAPTION / SECTION_CAPTION / IN_SCENE_NOTE
#       LEGEND_ITEMS / LEGEND_NOTE / LATERAL_GAP_COUNT / BOTTOM_GAP_COUNT / SCHEMATIC_GAP_FRACTION
#       Z_FRAME .. Z_TEXT / FACE_HIGHLIGHT_INSET

@dataclass(frozen=True)
class StructureMetrics:
    @classmethod
    def from_diameter(cls, diameter_mm: float) -> "StructureMetrics"

class _StructureItemBase(QtWidgets.QGraphicsItemGroup):
    metrics: StructureMetrics
    def _add(self, item): ...          # 设 NoButton + addToGroup + 返回 item

class TopViewStructureItem(_StructureItemBase):
    lateral_gap_markers: list          # 长度 4
    bottom_cap_hidden_marker: object   # 虚线隐藏轮廓
    texts: list[str]

class CrossSectionItem(_StructureItemBase):
    bottom_gap_marker: object
    lateral_gap_markers: list          # 长度 2
    lateral_gap_note: str              # 含 "前后两侧见俯视"
    texts: list[str]

class StructureView(QtWidgets.QGraphicsView):
    def __init__(self, item, parent=None): ...   # scene + fitInView + 非交互
    def _fit(self): ...                          # itemsBoundingRect + 边距，KeepAspectRatio

class TaxelFaceRectItem(QtWidgets.QGraphicsRectItem): ...
class TaxelFaceEllipseItem(QtWidgets.QGraphicsEllipseItem): ...

def scene_point(x_mm, y_mm); def scene_rect(...)
def iter_items(root); def text_items(root); def text_values(root)
def structure_texts(root) -> list[str]     # 含 "结构示意" 的文本
def dimension_texts(root) -> list[str]     # 命中"数字+mm/µm/μm/um/nm/pF/N"的文本（须为空）
`

StructureView._fit() 在 resizeEvent 与 showEvent 中调用，且 viewport 宽高 > 0 时才 fitInView（避免 0 尺寸 Qt 警告）；默认边距外扩。

**文字留白（评审修正）**：只按几何范围 fit 会把固定字号标签推到视口外。`_fit()` 必须先按几何 fit，再用当前变换比例 `m11()` 把每个 `ItemIgnoresTransformations` 文本的像素包围盒换算成场景单位（`px / scale`），与几何 rect 求并集后重 fit，迭代 2–3 次收敛；`setSceneRect` 同步扩展，避免滚动范围把标签夹掉。测试 `test_labels_fit_inside_the_default_panel_viewport` 断言每个标签的视口矩形都在 viewport 内。

TaxelFace* 绘制规则：

`python
class TaxelFaceRectItem(QtWidgets.QGraphicsRectItem):
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)      # 保留原 pen/brush 语义（含 NoBrush）
        _paint_face_highlight(painter, self.rect(), self.brush(), square=True)

class TaxelFaceEllipseItem(QtWidgets.QGraphicsEllipseItem):
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        _paint_face_highlight(painter, self.rect(), self.brush(), square=False)

FACE_HIGHLIGHT_INSET = 0.10
def _paint_face_highlight(painter, rect, brush, *, square):
    if brush.style() == QtCore.Qt.BrushStyle.NoBrush:
        return          # 云图模式只保留既有外框，不叠加装饰
    inset = FACE_HIGHLIGHT_INSET * min(rect.width(), rect.height())
    inner = rect.adjusted(inset, inset, -inset, -inset)
    if inner.isEmpty():
        return
    colour = with_alpha(TEXT_PRIMARY, 90)
    painter.save()
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.setPen(QtGui.QPen(colour, 0.0))          # 0 宽 = cosmetic 1 px
    if square:
        painter.drawRoundedRect(inner, inner.width() * 0.18, inner.height() * 0.18)
    else:
        painter.drawEllipse(inner)
    painter.restore()
`

约束：装饰必须画在 self.rect() 内；不得调用 prepareGeometryChange()；paint() 只读 item 状态，不得 setBrush/setPen。

### 2.11 反模式

- 用 QGraphicsItem + setTransform(scale(...)) 做外框（文字变形、bounding rect 与点击映射不一致）。
- 把结构图元叠加到 field_plot/sensor_plot 的场景里当装饰层（进入点击/命中路径）。
- 场景文本写 "0.2 mm"、"10 µm"、"pF" 等数值。
- 用载荷值给黄色活动板染色（破坏部件身份）。结构图做成随力变化的动画。
- 剖面里用箭头暗示"已测位移"。

---

## 3. pyqt_single_taxel.py 接线

### 3.1 布局（before → after）

现状（pyqt_single_taxel.py:173–196）：QVBoxLayout = [info_label, QHBoxLayout(sensor_plot stretch 5, force_plot stretch 6)]。

改为：

`text
central QWidget
└─ QVBoxLayout main_layout
   ├─ QHBoxLayout info_row                # 新增，仅为放切换按钮
   │  ├─ info_label            (stretch 1)   # 行 181-183，文本契约不变
   │  └─ structure_toggle QToolButton        # 新增，checkable，默认未选中
   └─ QHBoxLayout content_layout          # stretch 1
      ├─ QVBoxLayout left_column (stretch 5)   # 原 sensor_plot 的 stretch 5 迁到列
      │  ├─ sensor_plot        (stretch 1)     # 行 188-189
      │  ├─ field_legend_label (固定)          # 新增：力场编码说明，可换行
      │  └─ structure_panel    (stretch 0)     # 新增，默认隐藏
      └─ force_plot            (stretch 6)     # 行 191-192
`

- 面板放在**左侧列 sensor_plot 之下**，不新增横向列（横向加列会抬高最小宽度，与 800 px 折叠目标冲突）。
- structure_panel：objectName="StructurePanel"、panel_qss()、setMinimumWidth(0)、setMaximumHeight(300)、setVisible(False)。
- 面板内部（QVBoxLayout，margins 6）：①两个 StructureView 并排（structure_top_view / structure_section_view，各 setMinimumHeight(210)、setMinimumWidth(120)；面板 setMaximumHeight(400)）；②structure_legend = StructureLegendWidget()；③structure_caption = QLabel(SCHEMATIC_NOTE)（setWordWrap(True)、legend_qss()，常驻注记逐字来自设计文档第 151 行）。两个视图上方各加 QLabel（TOP_VIEW_CAPTION / SECTION_CAPTION），TEXT_MUTED、8–9pt。

### 3.2 折叠规则（800 px）

`python
STRUCTURE_MIN_WINDOW_WIDTH = 900

# __init__ 末尾（diameter_mm 校验之后）
self._structure_requested = False
self.structure_panel.setVisible(False)      # 默认折叠

def set_structure_details_visible(self, visible: bool) -> None:
    self._structure_requested = bool(visible)
    if self.structure_toggle.isChecked() != self._structure_requested:
        self.structure_toggle.blockSignals(True)
        self.structure_toggle.setChecked(self._structure_requested)
        self.structure_toggle.blockSignals(False)
    self._apply_structure_visibility()

def _structure_fits(self) -> bool:
    return self.width() >= STRUCTURE_MIN_WINDOW_WIDTH

def _apply_structure_visibility(self) -> None:
    show = self._structure_requested and self._structure_fits()
    self.structure_panel.setVisible(show)
    if self._structure_requested and not show:
        self.structure_toggle.setToolTip("窗口宽度不足 900 px，结构详情已折叠")

def resizeEvent(self, event):
    super().resizeEvent(event)
    if getattr(self, "structure_panel", None) is not None:
        self._apply_structure_visibility()
`

structure_toggle.toggled.connect(self.set_structure_details_visible)，默认 setChecked(False)。折叠是纯显示（不卸载场景/不销毁控件/不改 diameter_mm 与任何数据）；默认折叠时 minimumSizeHint 与现状一致，展开只占高度不占宽度。

**单点视图比例（评审修正）**：不要依赖 `setAspectLocked(True)`——pyqtgraph 0.14 在竖长控件里会把 ViewBox 几何撑出视口，Taxel 被裁掉一半。改为按 `ViewBox` 实际尺寸显式换算范围，并保证**两个方向都不裁掉受力面**：

```python
limit = diameter_mm * 0.9                 # 目标半程（> 半径，留边距）
aspect = view_box_width / view_box_height
y_limit = max(limit, limit / aspect)      # 窄高窗口把 Y 撑大，而不是缩小 X
x_limit = y_limit * aspect
setRange(xRange=(-x_limit, x_limit), yRange=(-y_limit, y_limit), padding=0.04)
```

重新计算的触发点：窗口 `resizeEvent`、`sensor_plot.viewport()` 的 `Resize` 事件过滤器（打开/收起面板时窗口不变但视图变）、以及每帧（仅在 ViewBox 尺寸变化时生效，避免与用户缩放打架）。回归测试 `test_sensor_view_never_crops_the_taxel`（240×800 与 900×600 两种极端）+ `test_sensor_units_stay_square_after_resize`。

### 3.3 不拦截点击

StructureView 是 sensor_plot 的兄弟 widget，不覆盖其绘制区；StructureView 设 setInteractive(False) + WA_TransparentForMouseEvents，场景内图元全部 NoButton（§2.9）；面板默认隐藏，展开只压缩 sensor_plot 的可见高度。

### 3.4 必须保持的契约

| 契约 | 位置 | 要求 |
|---|---|---|
| info_label 含 "fx = +40.00 N"、"fz = 100.00 N" | test_pyqt_single_taxel.py:83–84 | 不改第 352–357 行文案格式；结构注记放 structure_caption，不进 info_label |
| 矩形状态含 "20×20mm" 且不含 "Ø=20mm" | test_review_regressions.py:102–107 | 不改第 346–357 行 shape_size 分支 |
| taxel_item 仍为 QGraphicsRectItem/QGraphicsEllipseItem，.rect() 语义不变 | test_pyqt_single_taxel.py:87–93（第 92 行 isinstance） | 不替换第 214–217 行图元类型；本阶段 pyqt_single_taxel 不引入 TaxelFace* 子类（受力面身份由结构面板表达，零风险） |
| _update_sensor 先校验后绘制 | test_review_regressions.py:109–121 | 第 301–303 行校验必须仍在函数最前 |
| 箭头几何（头部贴线尾、方向一致） | test_review_regressions.py:82–100 | 只改第 232、244–245 颜色（可保持 3 px），不改角度/headLen/headWidth 逻辑（330–341） |
| 直径默认来自模型标称 | test_pyqt_single_taxel.py:95–99, 109–113 | 不改 --diameter-mm 默认（375）与 diameter_mm 属性 |

### 3.5 变更点清单

| 行 | 动作 |
|---|---|
| 3–13 | 增加 from ui_theme import ... / from sensor_structure_items import ... |
| 17–21 | FORCE_COLOURS 由 AXIS_COLOURS 派生（小写键） |
| 173–196 | 按 §3.1 改布局；插入 apply_window_theme、画布背景、_build_structure_panel() |
| 199–200 | 传感器图标题末尾追加 " | synthetic data · {self.scenario}"（来源标识；无测试断言该标题） |
| 211–220 | 图元类型/rect 参数不动；第 218–219 颜色改主题 |
| 232 / 244–245 | 箭头颜色高对比 |
| 257–260 | 选中轮廓 SELECTION_COLOUR |
| 265–284 | 图例文字色/字号；新增零位参考线（与 §4.5 同做法） |
| 300–357 | 301–303 校验不动；307–320 改调 field_ramp_colour；321 不动；352–357 文案不动 |
| 新增 | _build_structure_panel / set_structure_details_visible / _structure_fits / _apply_structure_visibility / resizeEvent |

---

## 4. pyqt_live.py 接线

### 4.1 受力面图元子类（不改几何、不改 .rect()）

现状：_setup_field_plot 在 pyqt_live.py:315–331 构造 QGraphicsEllipseItem（circle）或 QGraphicsRectItem（rectangle），参数来自 0.88 内缩计算（300–309），第 332–333 设笔/刷；点击定位不依赖图元命中（394–402 用 view 坐标 + locate_taxel）。

改法：**只替换构造用的类**，构造参数与 0.88 内缩逻辑一行不改：

`python
if self.taxel_shape == "circle":
    if inset_x > 0.0 and inset_y > 0.0:
        taxel_item = TaxelFaceEllipseItem(left + shrink_x / 2.0, bottom + shrink_y / 2.0,
                                          width - shrink_x, height - shrink_y)
    else:
        taxel_item = TaxelFaceEllipseItem(left, bottom, width, height)
else:
    taxel_item = TaxelFaceRectItem(left + shrink_x / 2.0, bottom + shrink_y / 2.0,
                                   width - shrink_x, height - shrink_y)
`

必须保持：

1. .rect() 数值/中心与改造前完全一致（test_pyqt_live.py:241–258 的 0.88 断言、260–283 的自然间隙断言）→ 不得重写 boundingRect()/shape()，paint() 不得 prepareGeometryChange()。
2. 图元类型仍是 QGraphicsRectItem/QGraphicsEllipseItem **子类**：test_pyqt_live.py:213 的 isinstance(..., QGraphicsEllipseItem) 必须继续成立（circle 模式）。
3. 云图 NoBrush 语义不变：第 478–480 行 setBrush(NoBrush) 后 test_pyqt_live.py:374–377 断言 brush().style() == NoBrush；paint() 在 NoBrush 时只走 super().paint()。
4. 第 615 行 setBrush(pg.mkBrush(colour)) 每帧着色通路不变（paint() 只读 self.brush()）。
5. zValue 保持默认 0（cloud_image -1、箭头 10/11、选中 20 均不动）。

### 4.2 高对比箭头

- pyqt_live.py:353：pen((30,30,30), width=2) → ARROW_LINE_COLOUR，宽度仍 2。
- pyqt_live.py:360–361：pen/brush((20,20,20)) → ARROW_COLOUR。
- 不改箭头尺寸（343–350）、方向角 angle_degrees - 180.0（639）、零剪切隐藏门限（626）。test_pyqt_live.py:554–597 只读 path 几何与位置，故不受颜色影响。
- 云图模式仍隐藏箭头（481–484）；阶段 A 不新增"云图矢量叠加"开关（阶段 B，设计文档第 229 行）。

### 4.3 标题文案（唯一来源，必须同步测试）

现状两处重复字面量：pyqt_live.py:283 与 :474，均为 f"{self.scenario} | colour=fz, black arrows=fx/fy"。改为常量 + 方法，两处都调用：

`python
ARRAY_TITLE_SUFFIX = "synthetic data | colour=fz, arrows=fx/fy"

def _array_title(self) -> str:
    return f"{self.scenario} | {ARRAY_TITLE_SUFFIX}"
`

云图标题（522–531）保留原前缀与量程后缀，只在末尾追加 " | synthetic data"（test_pyqt_live.py:378 的 "cloud | fz [N]"、429–430 的 "mz"/"N·m" 都是子串断言，不受影响）。

**必须同步修改的断言只有 1 条**：test_pyqt_live.py:420（见 §5.1）。措辞理由：箭头已改浅色，继续保留 "black arrows" 会误导（设计文档第 106、220 行要求同步修订文案，不得为旧断言保留错误文案）。

### 4.4 主题接线

| 行 | 动作 |
|---|---|
| 34–38 / 39–43 | 改由 ui_theme 提供（值不变） |
| 52–53 | TAXEL_PEN / CLOUD_TAXEL_PEN 取主题值 |
| 184 后 | apply_window_theme(self) |
| 196–199 | apply_canvas_theme(field_plot,"canvas")、apply_canvas_theme(right_plots,"panel") |
| 190 | selected_label 仅换色 + 等宽字体；padding 4px 保持（test_pyqt_live.py:108–120 的几何比较依赖该行尺寸） |
| 272 / 384 | 图例 labelTextColor / labelTextSize |

### 4.5 零位参考线与来源标识（阶段 A 第 1 条）

零位线：在 _setup_curve_plot（pyqt_live.py:377–392）内为每个曲线图加：

`python
zero = pg.InfiniteLine(
    angle=0, pos=0.0, movable=False,        # 水平线 = y 的零基准；angle=90 会画成 x=0 的竖线
    pen=pg.mkPen(ui_theme.ZERO_LINE_COLOUR, width=1, style=QtCore.Qt.PenStyle.DashLine),
)
zero.setZValue(-10.0)
plot.addItem(zero, ignoreBounds=True)     # 必须 ignoreBounds，避免改变 viewRange
`

pyqt_single_taxel._setup_force_plot（265–284）用同一段（该图 x 轴为距最新帧时间，0 即"现在"）。ignoreBounds=True 是硬要求：test_pyqt_live.py:158–176 断言 plot.viewRange() 覆盖全部合力/合力矩，零位线若参与自动量程会改变边界。

来源标识：**不要写进绘图标题**。pyqtgraph 用标题文本宽度参与 PlotItem 布局，长标题会把视图撑出视口并裁掉图元（实测原单点窗口最小宽度被顶到约 2175 px）。因此来源标识放在**窗口标题**（`setWindowTitle(... · synthetic data)`）与单元窗口的**可选换行信息栏**，绘图标题保持短。数据来自 live_source.py 生成器，标"合成数据"准确（设计文档第 128 行"已知数据源与显示状态"）。

力场编码说明：单元窗口标题改短后，`Colour=fz, Arrow=fx/fy` 不再写在标题里，改由 `field_legend_label`（QLabel，`setWordWrap(True)`、muted 样式）常驻在传感图下方：`"力场编码：颜色 = 法向力 fz（N）；箭头 = 切向力 (fx, fy)（N）"`。结构图例只解释部件身份色，不能替代力场编码说明。

### 4.6 不得改动清单

pyqt_live.py 中以下一律不动：56（GAP_RENDER_SCALE）、146–158（量程/色板上限）、160–179（模型与历史）、251–275（视图/通道按钮数量）、288–293（坐标范围/网格）、300–309（0.88 内缩计算）、337–339（选中轮廓 z/色）、370–373（云图 image z）、375（点击连接）、394–402（_on_field_click）、404–427（select_taxel 与 selected_label 文案格式）、429–452（advance_frame）、461–493 中除 474 标题外的全部分支、495–568（通道切换/量程/色条）、570–593（云图渲染）、595–648 中除 600–614 斜坡去重与 332/353/360 颜色外的全部逻辑、650–666（历史曲线）。

---

## 5. 测试变更清单

运行（README 第 137–138 行）：conda run -n taxel-pyqt python -m unittest test_cloud_field test_pyqt_live test_pyqt_single_taxel test_review_regressions（实现 PR 追加 test_ui_theme test_sensor_structure_items）。新 GUI 测试文件头必须 os.environ.setdefault("QT_QPA_PLATFORM", "offscreen") 与 os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")（同 test_pyqt_live.py:7–8）。

### 5.1 必须随显示行为同步修改（全部清单，仅 1 条）

| 文件:行 | 当前断言 | 需要的修改 | 备注 |
|---|---|---|---|
| test_pyqt_live.py:420 | assertIn("colour=fz, black arrows=fx/fy", window._field_title) | 改为 assertIn("colour=fz, arrows=fx/fy", window._field_title)，并追加 assertNotIn("black", window._field_title) | 只改这一条字符串；同一测试 410–419 行的图层恢复断言（视图模式、云图行隐藏、云图不可见、选中轮廓可见、brush != NoBrush、箭头杆/头可见）**一条不得删除或放宽** |

其余测试不因颜色/字体/图元子类/零位线而修改（新断言用子类语义与新文件表达）。若实现者擅自改 selected_label 文案格式或云图标题前缀，需另同步 test_pyqt_live.py:136、214、238、378、429–430——**本规格不允许**。

### 5.2 不得删除的力学/几何/时间/选择/布局断言（逐文件逐行）

test_pyqt_live.py（616 行）

| 行区间 | 保护内容 |
|---|---|
| 36–53 | 均匀夹持：合力/零力矩力学 |
| 55–72 | 右下四单元：三轴力矩闭式值 |
| 80–92 | 延迟帧真实时间 + PreciseTimer |
| 94–106 | 历史按真实年龄过期 |
| 108–120 | **800 px 工作区**、minimumSizeHint ≤ 800、wordWrap、标签在力场上方 |
| 122–137 | 选择切换后完整历史 + "row=2, col=0" 子串 |
| 139–141 | 非法参数拒绝 |
| 143–156 | clamp-slider 合力 |
| 158–176 | 有符号剪切/法向组合下 viewRange 覆盖 wrench（零位线必须 ignoreBounds） |
| 178–195 | bottom-right 合力矩 |
| 197–215 | circle 模式图元 isinstance QGraphicsEllipseItem（**子类必须成立**） |
| 217–239 | 非方阵单元/箭头数量、size=20×15 mm 子串 |
| 241–258 | **0.88 内缩的 .rect() 数值/中心**（渲染分隔语义） |
| 260–283 | 自然间隙时 .rect() == taxel_rect_mm |
| 291–312 | 力矩色条对称覆盖正负 |
| 314–326 | shear 色条与法向解耦 |
| 328–353 | fixed mz 覆盖剪切但不吹大 mx/my |
| 355–379 | 云图图层：NoBrush、箭头隐藏、选中可见、"cloud | fz [N]" |
| 381–394 | 云图模式右侧曲线仍随帧更新 |
| 396–421 | 返回阵列模式恢复图层（**仅 420 行改字符串**，410–419 不得删除） |
| 423–435 | 通道切换状态/标题/重绘 |
| 437–451 | 色条渐变必须等于 _cloud_lut() 的 stops 与整数色（主题不得改 LUT） |
| 453–533 | 自动量程攻击/衰减/固定量程/非法取值（含 453–462、464–478、480–493、495–512、514–533） |
| 535–551 | 非法 scale/view/channel 拒绝 |
| 554–597 | **箭头头部方向与线一致**（镜像缺陷回归；只允许改颜色/笔宽） |
| 600–612 | CLI 几何默认跟随模型标称 |

test_pyqt_single_taxel.py（117 行）

| 行区间 | 保护内容 |
|---|---|
| 22–31 | 单元历史有界/相对时间 |
| 35–43 / 45–54 | 生成器读数闭式值 |
| 62–85 | 曲线数据 + **info_label 文案契约（83–84）** |
| 87–93 | 矩形模式 taxel_item 为 QGraphicsRectItem（92） |
| 95–99 / 109–113 | 直径默认 = 模型标称（窗口与 CLI） |
| 101–105 | 非法参数拒绝 |

test_review_regressions.py（126 行）

| 行区间 | 保护内容 |
|---|---|
| 20–34 | 分数索引拒绝 / 整数值索引支持 |
| 37–44 | 未知场景 / 非有限时间拒绝 |
| 47–56 | 历史按年龄过期 |
| 64–68 | 非法 arrow_scale_mm_per_n 拒绝 |
| 70–80 | 延迟帧真实时间 + PreciseTimer |
| 82–100 | 单元箭头头部方向/贴尾几何 |
| 102–107 | 矩形状态文案用 × 不用 Ø= |
| 109–121 | _update_sensor 校验必须先于绘制 |

test_cloud_field.py（118 行）

| 行区间 | 保护内容 |
|---|---|
| 16–26 / 28–35 | 常量场插值 / NaN 排除 |
| 37–47 | 力矩通道和 == 已验证 wrench |
| 49–53 / 55–70 / 72–87 | 非法通道 / 朝向 / 非方阵 extent |
| 91–110 | **DIVERGING_LUT 锁定**（白中点、NaN 透明、上下端色） |
| 112–114 | 非法量程拒绝 |

### 5.3 新增测试（实现轮必须补）

test_ui_theme.py（新文件；offscreen）

1. test_surface_tokens_match_the_design_document：WINDOW_BG/PANEL_BG/CANVAS_BG 等于 #0B0F17/#111827/#0D131F（设计文档第 165 行）。
2. test_axis_and_moment_colour_keys_are_stable：键集合与旧 RGB 值。
3. test_mono_font_is_monospaced：styleHint == QFont.StyleHint.Monospace；mono_family_qss() 含 "monospace"。
4. test_window_qss_has_no_layout_metrics：window_qss() 不含 "padding"/"margin"/"min-width"/"font-size"（保护 800 px）。
5. test_field_ramp_colour_matches_the_previous_implementation：三端点值 + 0.225 处与旧公式逐通道相等。
6. test_apply_canvas_theme_sets_background_brush：QGraphicsView 上 backgroundBrush 颜色 == CANVAS_BG（验证不需要 pyqtgraph）。

test_sensor_structure_items.py（新文件；offscreen + QApplication）

1. test_metrics_scale_with_the_nominal_width：from_diameter(20) 各字段 == from_diameter(10) 的两倍；gap/span 两例相等。
2. test_gap_geometry_is_consistent：plate_bottom − bottom_electrode_top == gap；lateral_electrode_inner − plate_diameter/2 == gap；lateral_pad_inner − plate_diameter/2 == gap；lateral_pad_outer == frame_outer/2 − frame_ring。
3. test_no_item_accepts_mouse_buttons：iter_items 每项 acceptedMouseButtons() == NoButton；flags 不含 Selectable/Movable/Focusable。
4. test_no_physical_dimension_is_printed：两个图元 dimension_texts() == []；text_values 至少一条含 "结构示意"。
5. test_top_view_shows_four_lateral_gaps_and_the_hidden_bottom_capacitor：len(lateral_gap_markers) == 4；bottom_cap_hidden_marker 非空；文本含 "×4" 与 "底部电容 ×1"。
6. test_cross_section_shows_one_bottom_gap_and_two_side_gaps：bottom_gap_marker 存在；len(lateral_gap_markers) == 2；lateral_gap_note 含 "前后两侧见俯视"。
7. test_z_order_separates_part_identity_layers：Z_FRAME < Z_ELECTRODE < Z_SILICONE < Z_GAP < Z_PLATE < Z_FACE < Z_LEADER < Z_TEXT；plate/face 图元 z 对应。
8. test_structure_view_is_not_interactive：isInteractive() 为 False、WA_TransparentForMouseEvents 为真、scene().items() 非空。
9. test_structure_texts_use_the_design_wording：SCHEMATIC_NOTE 与设计文档第 151 行逐字一致。
10. test_face_items_keep_rect_and_paint_inside_it：TaxelFaceRectItem(0,0,10,10).rect() == QRectF(0,0,10,10)；boundingRect() == rect()；Ellipse 同理（防重写几何）。

**评审修正轮新增（2026-10-19 复核后）**

1. test_sensor_structure_items.py：`test_moving_plate_is_square_while_the_face_stays_round`（方形板、圆形受力面）、`test_four_lateral_gaps_line_up_with_the_square_plate_edges`、`test_labels_fit_inside_the_default_panel_viewport`。
2. test_pyqt_single_taxel.py：`test_sensor_view_never_crops_the_taxel`（窄高 + 常规两种窗口，X/Y 半程都 ≥ 半径，且比例仍等于 ViewBox 宽高比）、`test_force_plot_has_a_horizontal_zero_line`（angle == 0、value == 0）、`test_force_field_encoding_caption_is_present`。
3. test_pyqt_live.py：零位线断言改 `angle == 0`；新增 `test_array_title_drops_stale_black_arrow_wording` 之外，`test_curve_plots_have_a_zero_reference_line` 仍断言三张图各一条水平基线且不改变 viewRange。

test_pyqt_single_taxel.py 追加

1. test_structure_panel_starts_collapsed：structure_panel.isHidden() 为 True，toggle 未选中。
2. test_structure_panel_opens_on_wide_window：resize(1200, 680) 后 set_structure_details_visible(True) → isHidden() 为 False。
3. test_structure_panel_autocollapses_below_900_pixels：resize(800, 600) 后 set_structure_details_visible(True) → isHidden() 为 True（不依赖隐藏窗口的 resizeEvent 投递）。
4. test_structure_caption_is_the_mandated_note：structure_caption.text() == SCHEMATIC_NOTE。
5. test_structure_panel_does_not_intercept_the_force_plot：structure_top_view.isInteractive() 为 False、WA_TransparentForMouseEvents 为真。
6. test_taxel_item_semantics_are_unchanged：circle → isinstance QGraphicsEllipseItem；rectangle → isinstance QGraphicsRectItem；且 .rect().width() == diameter_mm。
7. test_info_label_contract_survives_the_structure_panel：断言 "fx = " 与 "fz = " 仍在（补充，不替代 83–84）。

test_pyqt_live.py 追加

1. test_taxel_face_items_are_graphics_item_subclasses：rectangle 模式 all(isinstance(..., QGraphicsRectItem))；circle 模式 all(isinstance(..., QGraphicsEllipseItem))（与既有 213 行并存，不替代）。
2. test_face_item_bounding_rect_equals_rect：默认几何下每项 boundingRect() == rect()。
3. test_array_title_drops_stale_black_arrow_wording：构造 + set_view("array") 后 assertIn("colour=fz, arrows=fx/fy", ...) 且 assertNotIn("black", ...)。
4. test_arrow_items_use_the_high_contrast_theme_colour：arrow_lines[0].pen().color() == qcolor(ARROW_LINE_COLOUR)。
5. test_curve_plots_have_a_zero_reference_line：每个曲线图存在 pg.InfiniteLine 且 pos().x() == 0，构造前后 viewRange() 不变（ignoreBounds 生效）。

### 5.4 编写注意

- 断言"面板是否显示"用 isHidden()（现有测试同样用法：test_pyqt_live.py:363、411），不要用 isVisible()（未 show() 的窗口其子控件 isVisible() 恒 False）。
- 本规格允许的"删除旧断言"数 = **0**，允许的"修改旧断言"数 = **1**（test_pyqt_live.py:420）。

---

## 6. 风险与回退

### 6.1 风险表

| 编号 | 风险 | 症状/证据 | 规避 |
|---|---|---|---|
| R1 | 800 px 最小宽度被抬高 | test_pyqt_live.py:108–120 失败 | ①window_qss() 禁止布局度量（测试 4 强制）②不新增按钮/控件行（来源标识用标题后缀）③selected_label 保持 wordWrap 与 padding 4px ④不改坐标轴 tick 字体 |
| R2 | 子类破坏 .rect() 语义或命中 | test_pyqt_live.py:241–258/260–283 失败 | 只重写 paint()；不重写 boundingRect/shape/mousePressEvent；构造参数原样传入；paint() 不 prepareGeometryChange() |
| R3 | 装饰图元吞掉点击 | 点击不再切换选择（pyqtgraph 仅 mouseGrabberItem() 为空时登记 click） | 全部 NoButton、非 selectable/movable/focusable；结构视图独立 widget + setInteractive(False) + WA_TransparentForMouseEvents；_on_field_click/locate_taxel 路径不动 |
| R4 | 云图 NoBrush 被自定义 paint 破坏 | test_pyqt_live.py:374–377、414–417 失败 | paint() 在 NoBrush 时只走 super().paint()；paint() 内不 setBrush |
| R5 | 主题改动破坏云图色条/色板一致性 | test_pyqt_live.py:291–353、437–451；test_cloud_field.py:91–110 失败 | ui_theme 不 import/不包装 cloud_field；_cloud_lut()、_cloud_pg_colour_map() 不动 |
| R6 | 零位线改变自动量程 | test_pyqt_live.py:158–176 失败 | plot.addItem(zero, ignoreBounds=True)；setZValue(-10)；不进图例 |
| R7 | 单元窗口最小宽度被结构面板抬高 | 窄屏不可用 | 面板放既有左列内（不新增列）、setMinimumWidth(0)、默认隐藏、<900 px 自动折叠 |
| R8 | 场景文本被 fitInView 缩放成不可读/溢出 | 文字巨大或重叠 | 文本 ItemIgnoresTransformations + 8pt；放 label_band 几何外；允许 ±10% 微调；详细图例用 QWidget |
| R9 | 隐藏窗口的 resizeEvent 不投递致测试误判 | 折叠测试偶发失败 | 测试直接调 set_structure_details_visible(True)，依赖 self.width()，不依赖未显示窗口的 resizeEvent |
| R10 | 等宽字体改变字宽导致几何偏移 | 800 px 或标签顺序失败 | 只对 selected_label/info_label 用 setFont（不全局）；字号 ≤10pt（原 15px 更大，方向安全）；必要时回退为仅颜色主题 |
| R11 | 未运行即宣称通过 | 违反证据边界 | 实现轮附实际命令与输出；无 taxel-pyqt 环境按 README 记录"受阻"，不安装/切换依赖冒充通过 |
| R12 | 结构画面被误读为实测结构 | 用户把示意当尺寸 | 场景 IN_SCENE_NOTE + 面板 SCHEMATIC_NOTE + 图例 LEGEND_NOTE 三处明示；dimension_texts 测试强制无尺寸数字；俯视图必须画"底部电容 ×1（板下）"隐藏轮廓 |

### 6.2 回退方案

1. 阶段 A 纯显示层：回退 = 删除 ui_theme.py、sensor_structure_items.py（及其两个测试文件），并 git checkout 2e39c10 -- pyqt_live.py pyqt_single_taxel.py test_pyqt_live.py test_pyqt_single_taxel.py。无数据迁移、不改模型/历史/文件格式。
2. 可按 §0 顺序逐块回退：结构面板（pyqt_single_taxel）与受力面子类/箭头/标题（pyqt_live）互不依赖，可单独撤销。
3. 回退后唯一需恢复的测试改动是 test_pyqt_live.py:420 的字符串（与产品文案成对）。
4. 任何情况下不得为了让显示通过而改 model.py / cloud_field.py 的数值或阈值（设计文档第 267 行"不修改传感器数据以迎合显示"）。

---

## 7. 验收清单（对应设计文档第 222 行退出标准；实现轮逐条给证据）

- [ ] 新增 ui_theme.py、sensor_structure_items.py；只改两个 GUI 模块与测试；git status 无 model.py/cloud_field.py/app.py/live_*.py/requirements*.txt 变更。
- [ ] test_ui_theme test_sensor_structure_items test_pyqt_live test_pyqt_single_taxel test_review_regressions test_cloud_field 全绿（附实际输出）。
- [ ] 阵列力场 / 单元俯视 / 单元剖面中：固定外框、中央黄色活动板、白色受力面三层身份可辨；四侧 + 底部共 5 个间隙可数；无任何间隙/位移/pF 数值。
- [ ] 800 px 断言（test_pyqt_live.py:108–120）通过；minimumSizeHint().width() ≤ 800。
- [ ] 选择、完整历史、真实时间、合力矩聚合、箭头方向回归（test_pyqt_live.py:80–195、554–597；test_review_regressions.py:70–100）通过。
- [ ] 云图色条/LUT 一致性（test_pyqt_live.py:291–353、437–451；test_cloud_field.py:91–110）通过且 cloud_field.py 未改。
- [ ] test_pyqt_live.py:420 已按新文案更新，且 assertNotIn("black", ...) 通过。
- [ ] 结构图元点击安全测试通过（NoButton、无 selectable/movable/focusable）。
- [ ] SCHEMATIC_NOTE 与设计文档第 151 行逐字一致。
- [ ] 未装新依赖、未切换环境冒充通过；无 GUI 手工"看起来对"替代自动断言。

---

## 附录 A 行号核对表（基线 2e39c10，逐文件读取核对）

| 引用 | 核对到的实际内容 | 设计文档引用 | 备注 |
|---|---|---|---|
| model.py:8 | CHANNELS = 3 | — | — |
| model.py:33–52 | ArrayGeometry dataclass + 校验 | — | — |
| model.py:35–40 | 默认 3×3 / 10 mm / 10 mm | — | 几何默认不得改 |
| model.py:87–96 | positions_m() 完整函数 | 87–95 | 设计文档少最后一行为收尾括号，本规格用 87–96 |
| model.py:98–106 | taxel_rect_mm() | — | 图元几何基准 |
| model.py:108–131 | locate_taxel()（circle/rectangle 命中） | — | 点击映射语义 |
| model.py:151–157 | validated_readings() | 151–157 | 一致 |
| model.py:208–213 | wrench() | 208–213 | 一致 |
| cloud_field.py:19–20 | CLOUD_CHANNELS / CHANNEL_UNITS | — | — |
| cloud_field.py:24–34 | SEQUENTIAL_LUT | — | 不得改 |
| cloud_field.py:35–45 | DIVERGING_LUT | — | test_cloud_field.py:91–110 锁定 |
| cloud_field.py:50–78 | channel_map()（mx/my/mz 在 71–78） | 71–78 | 一致（力矩段） |
| cloud_field.py:81–124 | interpolate_field() 完整函数 | 81–121 | 设计文档止于 field = np.where(...)（121），实际函数到 124（extent/return），本规格用 81–124 |
| cloud_field.py:127–156 | apply_lut() | — | — |
| live_history.py:29–36 | append() 校验段 | 29–36 | 一致（阶段 A 不改） |
| pyqt_live.py:32–56 | 组件/颜色/笔/0.88 常量 | — | 56 = GAP_RENDER_SCALE |
| pyqt_live.py:181–245 | _setup_window | — | — |
| pyqt_live.py:190 | selected_label 样式 font-size:15px; padding:4px | — | 改动点 |
| pyqt_live.py:247–275 | 视图/通道按钮（数量固定） | — | 不得新增按钮 |
| pyqt_live.py:281–375 | _setup_field_plot | — | — |
| pyqt_live.py:282–284 | 初始标题含 black arrows（283） | — | 改文案 |
| pyqt_live.py:288–293 | 坐标范围/网格/hideButtons | — | 不动 |
| pyqt_live.py:300–309 | 0.88 内缩计算 | — | 不得改 |
| pyqt_live.py:315–331 | 单元图元构造（rect/ellipse） | — | 换子类 |
| pyqt_live.py:332–333 | 图元笔/刷 | — | 主题色 |
| pyqt_live.py:337–339 | 选中轮廓（金色，z 20） | — | 不动 |
| pyqt_live.py:341–368 | 箭头（笔 353、头笔/刷 360–361、z 363–364） | — | 只换色 |
| pyqt_live.py:370–375 | 云图 image（z -1）与点击连接 | — | 不动 |
| pyqt_live.py:377–392 | _setup_curve_plot（图例 384） | — | 加零位线/图例色 |
| pyqt_live.py:394–402 | _on_field_click | — | 不得改 |
| pyqt_live.py:461–493 | set_view（标题 474、NoBrush 478–480、隐藏箭头 481–484） | — | 只改 474 |
| pyqt_live.py:509–541 | 云图量程/色板/色条映射 | — | 不得改 |
| pyqt_live.py:595–648 | _render_array_view（斜坡 600–614、刷 615、箭头 616–647） | — | 斜坡去重 |
| pyqt_single_taxel.py:16–22 | FORCE_COMPONENTS / FORCE_COLOURS / SCENARIOS | — | 颜色来源改主题 |
| pyqt_single_taxel.py:173–196 | _setup_window（info_label 181–183、content 185–186、plots 188–192） | — | 改布局 |
| pyqt_single_taxel.py:182 | info_label 样式 | — | 改字体/颜色 |
| pyqt_single_taxel.py:198–263 | _setup_sensor_plot（图元 214–217、箭头 232–248、轮廓 257–263） | — | 只改颜色 |
| pyqt_single_taxel.py:265–284 | _setup_force_plot（图例 272、曲线 276–280） | — | 加零位线 |
| pyqt_single_taxel.py:300–357 | _update_sensor（校验 301–303、斜坡 307–320、文案 346–357） | — | 斜坡去重，文案不动 |
| test_pyqt_live.py:108–120 | 800 px 测试 | 108–120 | 一致 |
| test_pyqt_live.py:197–283 | 图元几何兼容（圆/矩形/0.88/自然间隙） | 197–283 | 一致 |
| test_pyqt_live.py:355–379 | 云图图层 + "cloud | fz [N]" | 355–378 | 断言在 378，379 是 close()；本规格含收尾用 355–379 |
| test_pyqt_live.py:396–421 | 阵列图层恢复（420 为文案断言） | 396–420 | 421 为 close()；本规格用 396–421 |
| test_pyqt_live.py:437–451 | 色条渐变 == LUT | 437–449 | 断言延续到 450，close() 在 451；本规格用 437–451 |
| test_pyqt_live.py:420 | assertIn("colour=fz, black arrows=fx/fy", ...) | — | **唯一必须修改的断言** |
| test_pyqt_live.py:554–597 | 箭头方向回归 | — | 不得删除 |
| test_pyqt_single_taxel.py:83–84 | "fx = +40.00 N"、"fz = 100.00 N" | — | 文案契约 |
| test_pyqt_single_taxel.py:87–93 | 矩形 taxel_item isinstance（92） | — | 语义契约 |
| test_review_regressions.py:82–100 | 单元箭头方向 | — | 不得删除 |
| test_review_regressions.py:102–107 | 矩形文案 × 而非 Ø= | — | 不得删除 |
| test_review_regressions.py:109–121 | _update_sensor 校验顺序 | — | 不得删除 |
| test_cloud_field.py:91–110 | DIVERGING_LUT 锁定 | 91–110 | 一致 |
| README.md:137–138 | taxel-pyqt unittest 命令 | — | 实现 PR 追加新模块名 |
| requirements-pyqt.txt | pyqtgraph==0.14.0、PySide6==6.11.2 | — | 决定 LegendItem(labelTextColor=...) 与 InfiniteLine 可用性 |
| pyqtgraph 0.14.0 GraphicsScene.py | sigMouseClicked 仅在 mouseGrabberItem() is None 时登记 click（mousePressEvent）；sendClickEvent 末尾无条件 emit | — | 支撑 §2.9 点击安全论证 |
| pyqtgraph 0.14.0 ViewBox.py | 无 mousePressEvent；mouseClickEvent 只处理右键菜单 | — | 现状点击可用、新图元不得抢抓取 |
| pyqtgraph 0.14.0 GraphicsView.py:124 | setBackground(background) | — | apply_canvas_theme 依据 |
| pyqtgraph 0.14.0 LegendItem.py:36,168 | labelTextColor 参数与 setLabelTextColor | — | 图例配色依据 |

## 附录 B 本轮未执行事项（证据边界）

- 未修改任何产品 .py、测试或依赖；除本规格外不新增文件。
- 未运行 unittest、未启动 GUI（含 offscreen）、未安装/切换 conda 环境、未采集硬件数据。
- 行号核对方式为逐文件读取源码 + grep 定位；pyqtgraph API 结论来自读取 taxel-pyqt 环境内 0.14.0 源码，而非运行 GUI。
- 因此本文件不构成任何"测试通过/视觉效果已确认"的声明；这些必须由实现轮的实际运行输出提供。

---

## 附录 C 实现记录（2026-10-19，阶段 A 已落地）

实现者：Lead（集成与两个 GUI 模块）+ `stage-a-structure-impl`（`sensor_structure_items.py` 与其测试）。

改动文件：
- 新增 `ui_theme.py`、`sensor_structure_items.py`、`test_ui_theme.py`、`test_sensor_structure_items.py`
- 修改 `pyqt_live.py`、`pyqt_single_taxel.py`、`test_pyqt_live.py`、`test_pyqt_single_taxel.py`、`README.md`
- 未改：`model.py`、`cloud_field.py`、`live_source.py`、`live_history.py`、`app.py`、`rerun_live.py`、`requirements-*.txt`

验证（实跑，非声明）：
```text
QT_QPA_PLATFORM=offscreen conda run -n taxel-pyqt python -m unittest \
  test_cloud_field test_pyqt_live test_pyqt_single_taxel test_review_regressions \
  test_ui_theme test_sensor_structure_items
Ran 93 tests ... OK
```
唯一被修改的旧断言仍是 `test_pyqt_live.py` 的 `black arrows` → `arrows`（外加 `assertNotIn("black", ...)`）。

实现期发现并修正的三处规格外真实缺陷（均已加回归测试）：
1. **长标题撑宽 PlotItem**：pyqtgraph 用标题文本宽度参与布局，原 `Single Taxel ... | synthetic data · scenario` 标题把单点窗口最小宽度顶到约 2175 px；改短绘图标题、把来源/scenario 移到窗口标题与信息栏后，最小宽度降到约 260 px，800 px 窗口不再裁切。
2. **`setAspectLocked` 在竖长控件中裁掉 Taxel**：pyqtgraph 0.14 会把 ViewBox 几何撑出视口，导致单元圆/方块被裁。改为按 `ViewBox` 实际尺寸显式换算 X/Y 范围，并新增 `test_sensor_units_stay_square_after_resize`。
3. **结构面板改变绘图尺寸后未重算比例**：新增 `_fit_sensor_view()`，由 viewport resize 事件过滤器与每帧（尺寸变化时）触发。

已知未做（按规格留待阶段 B）：云图 `mz` 仍用被测试锁定的 `DIVERGING_LUT`，零值纯白在暗背景上偏亮；结构示意图在面板高度较小时标签仍偏挤。

### 评审修正轮（2026-10-19 复核后）

| 编号 | 问题 | 修正 |
|---|---|---|
| P1 | 黄色活动板被画成圆形，四侧间隙与圆弧边不一致 | 俯视活动板改为**方形**圆角矩形（边长 plate_diameter）；白色受力面保持圆形；同步更正本规格 §2.5 第 4 条 |
| P2 | 800×1000 窄高窗口裁掉受力面（横向仅约 ±4.80 mm） | `_fit_sensor_view` 改为 `y_limit = max(limit, limit/aspect)`、`x_limit = y_limit*aspect`，两个方向都完整包含受力面 |
| P2 | 零位参考线画成 x=0 竖线 | 两个入口均改为 `angle=0` 水平线；`test_curve_plots_have_a_zero_reference_line` 与新增单元窗口断言同步改为 0° |
| P2 | 默认窗口展开结构详情时标签被裁 | `StructureView._fit` 增加文字留白：按 `m11()` 把标签像素包围盒换算成场景单位并并入 fit rect，迭代收敛；新增标签可见性测试 |
| P2 | 单元力场“颜色=fz、箭头=fx/fy”说明丢失 | 新增 `field_legend_label` 常驻说明栏（可换行），补回力场编码含义；同步更正 §4.5 |

回归：`Ran 99 tests ... OK`（6 个测试模块，含新增 5 项评审回归）。仍未提交、未建分支。


