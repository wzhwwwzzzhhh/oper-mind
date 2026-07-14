#!/usr/bin/env python3
"""生成简洁架构示意图PDF"""

from fpdf import FPDF
import os

FONT_DIR = "C:/Windows/Fonts"
YAHEI = os.path.join(FONT_DIR, "msyh.ttc")
YAHEI_BOLD = os.path.join(FONT_DIR, "msyhbd.ttc")

OUTPUT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "docs",
    "架构示意图.pdf",
)


class SimplePDF(FPDF):
    def __init__(self):
        super().__init__("L", "mm", "A4")  # Landscape
        self.add_font("YaHei", "", YAHEI)
        self.add_font("YaHei", "B", YAHEI_BOLD)
        self.set_auto_page_break(False)

    def draw_rounded_box(self, x, y, w, h, fill_color, text="", text_color=(255,255,255), font_size=12, bold=True, align="C"):
        """画圆角矩形框"""
        self.set_fill_color(*fill_color)
        self.set_draw_color(180, 190, 200)
        # 圆角矩形用普通矩形代替（简化）
        self.rect(x, y, w, h, style="DF")
        if text:
            self.set_xy(x, y)
            self.set_font("YaHei", "B" if bold else "", font_size)
            self.set_text_color(*text_color)
            self.cell(w, h, text, align=align)

    def draw_arrow_down(self, x1, y1, y2):
        """向下箭头"""
        self.set_draw_color(100, 110, 120)
        self.set_line_width(0.8)
        y_mid = y1 + (y2 - y1) / 2
        self.line(x1, y1, x1, y2)
        # 箭头头
        self.line(x1, y2, x1 - 3, y2 - 4)
        self.line(x1, y2, x1 + 3, y2 - 4)

    def draw_arrow_right(self, x1, x2, y):
        """向右箭头"""
        self.set_draw_color(100, 110, 120)
        self.set_line_width(0.8)
        self.line(x1, y, x2, y)
        self.line(x2 - 4, y - 3, x2, y)
        self.line(x2 - 4, y + 3, x2, y)

    def draw_arrow_left(self, x1, x2, y):
        """向左箭头"""
        self.set_draw_color(100, 110, 120)
        self.set_line_width(0.8)
        self.line(x1, y, x2, y)
        self.line(x2 + 4, y - 3, x2, y)
        self.line(x2 + 4, y + 3, x2, y)


def build():
    pdf = SimplePDF()
    pdf.add_page()

    w = pdf.w
    h = pdf.h
    l_margin = 40
    r_margin = 40
    usable = w - l_margin - r_margin

    # ── 标题 ────
    pdf.set_font("YaHei", "B", 22)
    pdf.set_text_color(41, 128, 185)
    pdf.set_xy(l_margin, 12)
    pdf.cell(usable, 12, "多智能体运维诊断协作系统 — 系统架构", align="C")

    pdf.set_draw_color(41, 128, 185)
    pdf.set_line_width(0.8)
    pdf.line(l_margin, 28, w - r_margin, 28)

    # ── 层定义 ────
    # Y 坐标规划
    L1_TOP = 38   # Coordinator
    L2_TOP = 75   # Domain Agents
    L3_TOP = 120  # Debate + Reflection
    L4_TOP = 172  # Report

    # 色板
    C_COORD = (41, 128, 185)     # 蓝色
    C_SERVER = (46, 125, 50)     # 绿色
    C_DB = (230, 126, 34)        # 橙色
    C_LOG = (142, 68, 173)       # 紫色
    C_DEBATE = (192, 57, 43)     # 红色
    C_REFLECT = (243, 156, 18)   # 金色
    C_REPORT = (52, 73, 94)      # 深灰
    C_BG = (245, 247, 250)
    C_LABEL = (100, 100, 100)

    BOX_H = 16
    BOX_W = 100

    # ════════════════════════════════════════════════
    # Layer 1: Coordinator（横跨中间）
    # ════════════════════════════════════════════════
    coord_x = l_margin + 30
    coord_w = usable - 60
    pdf.set_fill_color(*C_BG)
    pdf.set_draw_color(200, 210, 220)
    pdf.rect(coord_x - 8, L1_TOP - 6, coord_w + 16, BOX_H + 22, style="D")

    pdf.draw_rounded_box(coord_x, L1_TOP, coord_w, BOX_H, C_COORD,
                         "Coordinator（动态路由调度器）", font_size=13)
    pdf.set_font("YaHei", "", 8)
    pdf.set_text_color(*C_LABEL)
    pdf.set_xy(coord_x + 5, L1_TOP + BOX_H + 2)
    pdf.cell(coord_w, 5, "直达（问题明确→目标 Agent）  |  链式（逐层排查）  |  并行（全面检查）", align="C")

    # Layer 1 → Layer 2 箭头
    arrow_y1 = L1_TOP + BOX_H + 10
    arrow_y2 = L2_TOP - 6
    center_x = w / 2
    pdf.draw_arrow_down(center_x, arrow_y1, arrow_y2)

    # ════════════════════════════════════════════════
    # Layer 2: 三个 Domain Agent
    # ════════════════════════════════════════════════
    agent_positions = [
        (l_margin + 10, C_SERVER, "Server Agent", "CPU / 内存 / 磁盘 / IO"),
        (w / 2 - BOX_W / 2, C_DB, "DB Agent", "慢 SQL / 索引 / 锁 / 连接池"),
        (w - r_margin - BOX_W - 10, C_LOG, "Log Agent", "错误日志 / 异常模式 / 慢查询日志"),
    ]

    for ax, acolor, aname, adesc in agent_positions:
        pdf.draw_rounded_box(ax, L2_TOP, BOX_W, BOX_H, acolor, aname, font_size=12)
        pdf.set_font("YaHei", "", 8)
        pdf.set_text_color(*C_LABEL)
        pdf.set_xy(ax, L2_TOP + BOX_H + 2)
        pdf.cell(BOX_W, 5, adesc, align="C")

    # Layer 2 → Layer 3 箭头
    arrow_y3 = L2_TOP + BOX_H + 10
    arrow_y4 = L3_TOP - 6
    for ax, _, _, _ in agent_positions:
        pdf.draw_arrow_down(ax + BOX_W / 2, arrow_y3, arrow_y4)

    # ════════════════════════════════════════════════
    # Layer 3: Debate + Reflection（并行排列）
    # ════════════════════════════════════════════════
    debate_w = 130
    reflect_w = 130
    gap = 16
    total_3w = debate_w + gap + reflect_w
    start_3x = (w - total_3w) / 2

    # Debate
    pdf.draw_rounded_box(start_3x, L3_TOP, debate_w, BOX_H, C_DEBATE,
                         "Debate Arena（辩论场）", font_size=11)
    pdf.set_font("YaHei", "", 8)
    pdf.set_text_color(*C_LABEL)
    pdf.set_xy(start_3x, L3_TOP + BOX_H + 2)
    pdf.cell(debate_w, 5, "多 Agent 意见不一致时触发辩论", align="C")
    pdf.set_xy(start_3x, L3_TOP + BOX_H + 8)
    pdf.cell(debate_w, 5, "各自提供证据 → 裁决达成共识", align="C")

    # →
    pdf.set_font("YaHei", "B", 16)
    pdf.set_text_color(150)
    pdf.set_xy(start_3x + debate_w, L3_TOP + 1)
    pdf.cell(gap, BOX_H, "→", align="C")

    # Reflection
    pdf.draw_rounded_box(start_3x + debate_w + gap, L3_TOP, reflect_w, BOX_H, C_REFLECT,
                         "Reflection（反思复审）", font_size=11)
    pdf.set_font("YaHei", "", 8)
    pdf.set_text_color(*C_LABEL)
    pdf.set_xy(start_3x + debate_w + gap, L3_TOP + BOX_H + 2)
    pdf.cell(reflect_w, 5, "交叉审核：各 Agent 互审报告对应部分", align="C")
    pdf.set_xy(start_3x + debate_w + gap, L3_TOP + BOX_H + 8)
    pdf.cell(reflect_w, 5, "有遗漏 → 退回修改；通过 → 输出", align="C")

    # Layer 3 → Layer 4 箭头
    arrow_y5 = L3_TOP + BOX_H + 16
    arrow_y6 = L4_TOP - 6
    pdf.draw_arrow_down(center_x, arrow_y5, arrow_y6)

    # ════════════════════════════════════════════════
    # Layer 4: Report Agent
    # ════════════════════════════════════════════════
    pdf.draw_rounded_box(center_x - 60, L4_TOP, 120, BOX_H, C_REPORT,
                         "Report Agent（报告生成）", font_size=12)

    # ── 右侧补充说明 ────
    pdf.set_font("YaHei", "", 9)
    pdf.set_text_color(*C_LABEL)
    pdf.set_xy(center_x - 60, L4_TOP + BOX_H + 4)
    pdf.cell(120, 5, "根因总结 / 诊断依据 / 优化建议 / 指标", align="C")

    # ── 底部流程图说明 ────
    flow_y = h - 30
    pdf.set_draw_color(200, 210, 220)
    pdf.set_line_width(0.4)
    pdf.line(l_margin, flow_y - 8, w - r_margin, flow_y - 8)

    pdf.set_font("YaHei", "B", 9)
    pdf.set_text_color(41, 128, 185)
    pdf.set_xy(l_margin, flow_y - 6)
    pdf.cell(usable, 5, "完整协作流程")

    flow_text = "用户提问  →  Coordinator 路由决策  →  领域 Agent 执行诊断  →  [Debate 辩论 →]  Reflection 复审  →  Report Agent 输出报告"
    pdf.set_font("YaHei", "", 9)
    pdf.set_text_color(100)
    pdf.set_xy(l_margin, flow_y + 2)
    pdf.cell(usable, 5, flow_text, align="C")

    # ── 路由策略说明标签 ────
    label_y = h - 12
    labels = [
        ("直达", "问题明确指向某领域 → 直接路由", C_SERVER),
        ("链式", "问题模糊 → 逐层推理", C_DB),
        ("并行", "全面检查 → 同时分发多 Agent", C_LOG),
    ]
    x_start = l_margin + 30
    for i, (name, desc, color) in enumerate(labels):
        lx = x_start + i * 160
        pdf.set_fill_color(*color)
        pdf.set_font("YaHei", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(16, 5, " " + name, fill=True)
        pdf.set_font("YaHei", "", 8)
        pdf.set_text_color(*C_LABEL)
        pdf.set_xy(lx + 18, label_y)
        pdf.cell(140, 5, desc)

    # ── 输出 ────
    pdf.output(OUTPUT)
    print(f"PDF 已生成：{OUTPUT}")
    print(f"文件大小：{os.path.getsize(OUTPUT) / 1024:.1f} KB")


if __name__ == "__main__":
    build()
