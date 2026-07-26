#!/usr/bin/env python3
"""生成项目方案说明书 PDF（面向毕设老师汇报用）"""

from fpdf import FPDF
import os

try:
    from scripts._bootstrap import PROJECT_ROOT
except ModuleNotFoundError:
    from _bootstrap import PROJECT_ROOT

# ── 字体路径 ──────────────────────────────────────────────────
FONT_DIR = "C:/Windows/Fonts"
YAHEI = os.path.join(FONT_DIR, "msyh.ttc")
YAHEI_BOLD = os.path.join(FONT_DIR, "msyhbd.ttc")
SIMSUN = os.path.join(FONT_DIR, "simsun.ttc")

OUTPUT = str(PROJECT_ROOT / "docs" / "项目方案说明书-汇报版.pdf")


class ProposalPDF(FPDF):
    def __init__(self):
        super().__init__("P", "mm", "A4")
        # 注册中文字体
        self.add_font("YaHei", "", YAHEI, uni=True)
        self.add_font("YaHei", "B", YAHEI_BOLD, uni=True)
        self.add_font("SimSun", "", SIMSUN, uni=True)
        self.set_auto_page_break(True, 20)

    # ── 辅助方法 ──────────────────────────────────────────────

    def cover_page(self):
        """封面"""
        self.add_page()
        w = self.w
        # 顶部装饰线
        self.set_draw_color(41, 128, 185)
        self.set_line_width(2)
        self.line(25, 40, w - 25, 40)

        # 主标题
        self.set_y(55)
        self.set_font("YaHei", "B", 28)
        self.set_text_color(41, 128, 185)
        self.cell(0, 14, "多智能体运维诊断协作系统", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("YaHei", "", 14)
        self.set_text_color(100)
        self.cell(0, 10, "基于大模型的多智能体协作框架", align="C", new_x="LMARGIN", new_y="NEXT")

        # 副标题
        self.ln(8)
        self.set_draw_color(200)
        self.set_line_width(0.5)
        self.line(60, self.get_y(), w - 60, self.get_y())
        self.ln(8)
        self.set_font("YaHei", "", 16)
        self.set_text_color(60)
        self.cell(0, 10, "—— 应用于运维故障诊断场景", align="C", new_x="LMARGIN", new_y="NEXT")

        # 项目定位标签
        self.ln(16)
        self.set_font("YaHei", "B", 13)
        self.set_text_color(41, 128, 185)
        self.cell(0, 8, "毕业设计 · 项目方案说明书", align="C", new_x="LMARGIN", new_y="NEXT")

        # 底部信息
        self.ln(50)
        self.set_font("YaHei", "", 11)
        self.set_text_color(120)
        self.cell(0, 7, "王  志  海", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, "2026 年 7 月", align="C", new_x="LMARGIN", new_y="NEXT")

        # 底部装饰线
        self.set_draw_color(41, 128, 185)
        self.set_line_width(2)
        self.line(25, self.get_y() + 6, w - 25, self.get_y() + 6)

    def section_title(self, num, title):
        """一级标题"""
        self.ln(4)
        self.set_font("YaHei", "B", 16)
        self.set_text_color(41, 128, 185)
        text = f"{num}  {title}" if num else title
        self.cell(0, 10, text, new_x="LMARGIN", new_y="NEXT")

        # 下划线
        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.6)
        y = self.get_y()
        self.line(self.l_margin, y, self.l_margin + 50, y)
        self.ln(4)

    def sub_title(self, title):
        """二级标题"""
        self.ln(2)
        self.set_font("YaHei", "B", 13)
        self.set_text_color(52, 73, 94)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def sub_sub_title(self, title):
        """三级标题"""
        self.set_font("YaHei", "B", 11)
        self.set_text_color(52, 73, 94)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        """正文"""
        self.set_font("YaHei", "", 10)
        self.set_text_color(60)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bullet(self, text, indent=10):
        """项目符号"""
        x0 = self.l_margin + indent
        self.set_x(x0)
        self.set_font("YaHei", "", 10)
        self.set_text_color(60)
        bullet_char = "●"
        self.cell(5, 5.5, bullet_char)
        self.multi_cell(0, 5.5, text)

    def numbered_item(self, num, text, indent=10):
        """编号条目"""
        x0 = self.l_margin + indent
        self.set_x(x0)
        self.set_font("YaHei", "", 10)
        self.set_text_color(60)
        self.cell(8, 5.5, num)
        self.multi_cell(0, 5.5, text)

    def info_table(self, rows, col_widths=None):
        """简单信息表格"""
        if col_widths is None:
            col_widths = [35, 0]
        self.set_font("YaHei", "", 10)
        for row in rows:
            self.set_text_color(60)
            # 表头列
            self.set_font("YaHei", "B", 10)
            self.set_text_color(41, 128, 185)
            self.cell(col_widths[0], 6, row[0])
            # 内容列
            self.set_font("YaHei", "", 10)
            self.set_text_color(60)
            if len(col_widths) > 1 and col_widths[1] == 0:
                self.multi_cell(0, 6, row[1])
            else:
                self.cell(col_widths[1], 6, row[1])
            self.ln(4)

    def architecture_box(self, lines, x=None, w=None):
        """用方框字符绘制简单的架构图"""
        if x is None:
            x = self.l_margin + 15
        if w is None:
            w = self.w - self.l_margin - x - 15
        self.set_x(x)
        # 灰底框
        self.set_fill_color(245, 247, 250)
        self.set_draw_color(180, 190, 200)
        y0 = self.get_y()
        self.set_font("YaHei", "", 8.5)
        self.set_text_color(50)
        for line in lines:
            self.set_x(x)
            self.cell(w, 4.8, "  " + line, new_x="LMARGIN", new_y="NEXT")
        y1 = self.get_y()
        # 画矩形背景
        self.set_fill_color(245, 247, 250)
        self.rect(x, y0, w, y1 - y0, style="F")
        self.set_draw_color(200, 210, 220)
        self.rect(x, y0, w, y1 - y0, style="D")
        # 重新输出文字（在背景之上）
        self.set_y(y0)
        for line in lines:
            self.set_x(x + 2)
            self.set_font("YaHei", "", 8.5)
            self.set_text_color(50)
            self.cell(w - 2, 4.8, line, new_x="LMARGIN", new_y="NEXT")
        self.set_y(y1 + 3)

    def check_page_space(self, needed_mm=40):
        """检查剩余空间，不够则分页"""
        if self.get_y() > self.h - needed_mm:
            self.add_page()

    def colored_cell(self, w, h, text, color, bold=False):
        """带背景色的单元格"""
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("YaHei", "B" if bold else "", 9)
        self.cell(w, h, text, align="C", fill=True)


def build(pdf: ProposalPDF):
    # ══════════════════════════════════════════════════════════
    # 封面
    # ══════════════════════════════════════════════════════════
    pdf.cover_page()

    # ══════════════════════════════════════════════════════════
    # 一、项目概述
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("一", "项目概述")

    pdf.sub_title("1.1 背景与问题")
    pdf.body_text(
        "现代运维体系中，一次故障排查通常涉及多个数据源：服务器指标（CPU、内存）、数据库状态"
        "（慢 SQL、锁等待）、日志文件（错误异常）。工程师需要在多个平台间手动切换、关联信息"
        "才能定位根因，效率低、门槛高。"
    )
    pdf.body_text(
        '本项目的目标：让多个 AI Agent 自动完成「全面排查 → 辩论共识 → 反思复审 → 输出报告」'
        '的完整闭环，将运维诊断从「人工翻查」升级为「智能协作」。'
    )

    pdf.sub_title("1.2 项目定位")
    pdf.info_table([
        ("毕业设计方向", "大模型与多智能体"),
        ("核心贡献", "多 Agent 协作模式（直达/链式/并行）的设计与对比实验"),
        ("项目类型", "框架 + 应用，以运维诊断为落地场景"),
        ("与 Java 版区别", "Java 版是单 Agent + 多工具；本毕设聚焦多 Agent 协作模式研究"),
    ])

    # ══════════════════════════════════════════════════════════
    # 二、技术栈
    # ══════════════════════════════════════════════════════════
    pdf.check_page_space(60)
    pdf.section_title("二", "技术栈")

    pdf.info_table([
        ("主语言", "Python 3.10+ — 大模型生态丰富，快速迭代"),
        ("Agent 编排", "LangGraph — 原生支持多 Agent 图编排"),
        ("LLM 部署", "Ollama（本地运行）— 无需外网 API，演示稳定"),
        ("API 层", "FastAPI — Agent 能力暴露 + 前端对接"),
        ("前端", "React 18 + TypeScript + Ant Design + ECharts"),
        ("数据源", "psutil（服务器实时指标）+ MySQL 真实连接 + 日志文件"),
    ])

    # ══════════════════════════════════════════════════════════
    # 三、系统架构
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("三", "系统架构 — 四层协作模型")

    pdf.body_text(
        "系统采用四层架构：Coordinator 动态路由 → 领域 Agent 执行诊断 → 质量保障机制（Debate "
        "+ Reflection）→ Report Agent 输出报告。"
    )

    pdf.sub_title("3.1 Coordinator — 三种路由策略")
    pdf.body_text(
        'Coordinator 作为「总指挥」，由 LLM 根据用户问题动态决策路由策略：'
    )

    pdf.set_font("YaHei", "", 10)
    pdf.set_text_color(60)

    # 直达
    pdf.set_fill_color(232, 245, 233)
    pdf.set_text_color(46, 125, 50)
    pdf.set_font("YaHei", "B", 10)
    y0 = pdf.get_y()
    pdf.cell(14, 6, "  ", fill=True)
    pdf.set_fill_color(232, 245, 233)
    pdf.cell(24, 6, " 直达策略", fill=True)
    pdf.set_font("YaHei", "", 10)
    pdf.set_text_color(60)
    pdf.cell(0, 6, " 问题明确指向某个领域 → 直接路由目标 Agent", new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(245, 245, 245)
    pdf.set_x(pdf.l_margin + 38)
    pdf.set_font("YaHei", "", 9)
    pdf.set_text_color(100)
    pdf.cell(0, 5, '例："这个 SQL 为什么慢？" → DB Agent', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # 链式
    pdf.set_fill_color(227, 242, 253)
    pdf.set_text_color(21, 101, 192)
    pdf.set_font("YaHei", "B", 10)
    pdf.cell(14, 6, "  ", fill=True)
    pdf.set_fill_color(227, 242, 253)
    pdf.cell(24, 6, " 链式策略", fill=True)
    pdf.set_font("YaHei", "", 10)
    pdf.set_text_color(60)
    pdf.cell(0, 6, " 问题模糊 → 逐层推理追查根因", new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(245, 245, 245)
    pdf.set_x(pdf.l_margin + 38)
    pdf.set_font("YaHei", "", 9)
    pdf.set_text_color(100)
    pdf.cell(0, 5, '例："系统很慢" → Server Agent → DB Agent → Log Agent', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # 并行
    pdf.set_fill_color(255, 243, 224)
    pdf.set_text_color(230, 126, 34)
    pdf.set_font("YaHei", "B", 10)
    pdf.cell(14, 6, "  ", fill=True)
    pdf.set_fill_color(255, 243, 224)
    pdf.cell(24, 6, " 并行策略", fill=True)
    pdf.set_font("YaHei", "", 10)
    pdf.set_text_color(60)
    pdf.cell(0, 6, " 需要全面检查 → 同时分发到多个 Agent", new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(245, 245, 245)
    pdf.set_x(pdf.l_margin + 38)
    pdf.set_font("YaHei", "", 9)
    pdf.set_text_color(100)
    pdf.cell(0, 5, '例："大促结束，全链路体检"', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.sub_title("3.2 领域 Agent")
    pdf.body_text("每个 Agent 拥有独立工具集，专精一个诊断维度：")

    pdf.sub_sub_title("Server Agent — 服务器诊断")
    pdf.set_font("YaHei", "", 9.5)
    pdf.set_text_color(60)
    pdf.body_text(
        "check_cpu() / check_memory() / check_disk() / "
        "check_process() / check_thread() / check_network()    数据源：psutil"
    )

    pdf.sub_sub_title("DB Agent — 数据库诊断")
    pdf.body_text(
        "EXPLAIN 分析 / 索引检测 / SHOW PROCESSLIST / "
        "连接池监控 / 慢查询终止（高危需审批）    数据源：MySQL"
    )

    pdf.sub_sub_title("Log Agent — 日志分析")
    pdf.body_text(
        "关键字检索 / 错误聚合 / 异常模式发现 / 慢查询日志分析    数据源：日志文件 + MySQL slow_log"
    )

    # ══════════════════════════════════════════════════════════
    # 四、质量保障机制
    # ══════════════════════════════════════════════════════════
    pdf.check_page_space(55)
    pdf.section_title("四", "质量保障机制")

    pdf.sub_title("4.1 Debate Arena（辩论场 — 可选触发）")
    pdf.body_text(
        "当并行模式下多个 Agent 诊断结论不一致时触发。各 Agent 提供证据辩护，"
        "Coordinator 或投票机制裁决，最终达成共识。"
    )
    pdf.body_text(
        "设计意义：当多个专家意见不一时，单一 Agent 结论不可信。通过辩论让证据说话，提升诊断可信度。"
    )

    pdf.sub_title("4.2 Reflection（反思复审 — 必备流程）")
    pdf.body_text(
        "每份诊断报告生成后，其他 Agent 交叉审核对应部分：DB Agent 审核数据库证据、"
        "Server Agent 审核服务器证据、Log Agent 审核日志是否支持结论。有遗漏则退回修改。"
    )
    pdf.body_text(
        '设计意义：单一 Agent 可能有盲区或误判，交叉复审相当于「提交前 Review 代码」，'
        '是质量保证的最后一道防线。'
    )

    # ══════════════════════════════════════════════════════════
    # 五、完整协作流程示例
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("五", "完整协作流程示例")

    pdf.sub_title('例：直达模式 — 「这个 SQL 为什么慢？」')
    pdf.architecture_box([
        "用户：帮我分析这个 SQL：SELECT * FROM orders WHERE status = 'PENDING'",
        "    │",
        "Coordinator：路由策略 = 直达，目标 = DB Agent",
        "    │",
        "DB Agent：",
        "  ① explain_sql → type=ALL 全表扫描",
        "  ② show_create_table → status 字段无索引",
        "  ③ 综合判断：缺索引导致全表扫描",
        "    │",
        "Reflection → 审核通过 → 输出报告",
    ])

    pdf.sub_title('例：链式模式 — 「系统很慢，经常超时」')
    pdf.architecture_box([
        "Step 1 — Server Agent：CPU 80%，MySQL 进程占 50%",
        "  → 初步判断：MySQL 负载高是瓶颈",
        "",
        "Step 2 — DB Agent：大量 SELECT WHERE status='PENDING'",
        "  → explain 全表扫描 50000 行，status 字段缺索引",
        "",
        "Step 3 — Log Agent：大量连接超时日志，慢查询反复出现",
        "  → 判断：慢 SQL 导致了连锁反应",
        "",
        "Final → Reflection → Report（缺索引→全表扫描→CPU飙升→超时）",
    ])

    pdf.sub_title('例：并行模式 — 「检查系统整体健康度」')
    pdf.architecture_box([
        "用户：明天大促，帮我看看整体健康度",
        "    │",
        "Coordinator：并行分发到所有 Agent",
        "    │",
        "Server Agent → CPU/内存/磁盘 全部正常",
        "DB Agent    → 有慢查询风险（status 缺索引）",
        "Log Agent   → 无明显异常",
        "    │",
        "结论一致 → 无需 Debate → Reflection → Report",
        "建议：系统整体健康，上线前给 status 加索引",
    ])

    # ══════════════════════════════════════════════════════════
    # 六、实施计划
    # ══════════════════════════════════════════════════════════
    pdf.check_page_space(70)
    pdf.section_title("六", "实施计划")

    plan_data = [
        ("P1", "LangGraph 多 Agent 框架搭建", "多 Agent 原型可运行", "2 周"),
        ("P2", "DB Agent — MySQL 真实连接", "DB Agent 可诊断", "1 周"),
        ("P3", "Server Agent — psutil 采集", "Server Agent 可用", "1 周"),
        ("P4", "Log Agent — 日志解析", "Log Agent 可用", "1 周"),
        ("P5", "Debate + Reflection 机制", "质量保障层跑通", "2 周"),
        ("P6", "Report Agent + 结构化报告", "报告引擎完成", "1 周"),
        ("P7", "前端可视化 React + TS", "前端可展示", "2 周"),
        ("P8", "复合测试 + 对比实验", "实验数据 + 分析", "2 周"),
        ("P9", "论文撰写 + 答辩准备", "论文定稿", "3 周"),
    ]

    # 画甘特风格表格
    pdf.set_font("YaHei", "B", 9)
    col_w = [16, 72, 56, 26]
    headers = ["阶段", "内容", "交付物", "时间"]
    pdf.set_fill_color(41, 128, 185)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, " " + h, align="C", fill=True)
    pdf.ln()

    row_colors = [(255, 255, 255), (245, 247, 250)]
    for idx, row in enumerate(plan_data):
        bg = row_colors[idx % 2]
        pdf.set_fill_color(*bg)
        pdf.set_text_color(60)
        pdf.set_font("YaHei", "B", 9)
        pdf.cell(col_w[0], 6, " " + row[0], fill=True)
        pdf.set_font("YaHei", "", 9)
        pdf.cell(col_w[1], 6, " " + row[1], fill=True)
        pdf.cell(col_w[2], 6, " " + row[2], fill=True)
        pdf.cell(col_w[3], 6, " " + row[3], align="C", fill=True)
        pdf.ln()

    pdf.ln(3)

    # ══════════════════════════════════════════════════════════
    # 七、论文结构建议
    # ══════════════════════════════════════════════════════════
    pdf.check_page_space(55)
    pdf.section_title("七", "论文结构建议")

    thesis_structure = [
        ("摘要", ""),
        ("第一章  绪论", "研究背景 / 国内外现状 / 本文工作"),
        ("第二章  相关技术", "LLM + Function Calling / 多智能体协作 / LangGraph / 运维诊断"),
        ("第三章  系统设计", "四层架构 / 动态路由 / 领域 Agent / 质量保障 / 报告生成"),
        ("第四章  系统实现", "Agent 框架 / 各领域 Agent / 协作机制 / 前端可视化"),
        ("第五章  实验与评估", "三种协作模式对比 / Debate 有效性 / Reflection 影响分析"),
        ("第六章  总结与展望", ""),
    ]

    pdf.set_font("YaHei", "", 10)
    pdf.set_text_color(60)
    for chapter, desc in thesis_structure:
        pdf.set_font("YaHei", "B", 10)
        pdf.set_text_color(52, 73, 94)
        pdf.cell(70, 6.5, "  " + chapter)
        pdf.set_font("YaHei", "", 10)
        pdf.set_text_color(100)
        pdf.cell(0, 6.5, desc)
        pdf.ln(5.5)

    pdf.ln(3)

    # ══════════════════════════════════════════════════════════
    # 八、创新点与亮点
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("八", "项目创新点与亮点")

    highlights = [
        ("多 Agent 协作模式研究",
         "设计并实现三种路由策略（直达/链式/并行），通过对比实验验证各模式在不同场景下的"
         "效果差异，而非单一功能实现。"),
        ("Debate + Reflection 双保险",
         "引入多 Agent 辩论机制解决意见分歧，Reflection 交叉复审确保报告质量。"
         "这两层机制在现有运维诊断系统中较为鲜见。"),
        ("真实数据源驱动",
         "使用 psutil 实时采集服务器指标、真实 MySQL 连接、本地日志文件作为数据源，"
         "避免 Mock 数据，诊断结果真实可信。"),
        ('完整闭环体验',
         '从「用户提问」到「诊断报告输出」形成完整闭环，前端可视化展示诊断链路与指标图表，'
         '直观易用。'),
    ]

    for title, desc in highlights:
        pdf.check_page_space(25)
        pdf.set_fill_color(232, 242, 254)
        pdf.set_text_color(41, 128, 185)
        pdf.set_font("YaHei", "B", 11)
        pdf.cell(0, 8, "  " + title, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("YaHei", "", 10)
        pdf.set_text_color(60)
        pdf.set_x(pdf.l_margin + 5)
        pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 5, 5.5, desc)
        pdf.ln(4)

    # ══════════════════════════════════════════════════════════
    # 九、待确认事项
    # ══════════════════════════════════════════════════════════
    pdf.ln(2)
    pdf.section_title("九", "待确认事项（与导师讨论）")

    items = [
        "论文题目方向是否合适",
        "Agent 数量：DB + Server + Log 起步是否够用",
        "是否需要扩展到 Redis / MQ Agent",
        "Debate 机制的具体形式（投票制 / Coordinator 裁决 / 其他）",
        "实验对比维度（准确率 / 耗时 / 用户满意度）",
        "时间节点和里程碑要求",
    ]
    for item in items:
        pdf.bullet(item)
        pdf.ln(1)

    pdf.ln(10)
    pdf.set_font("YaHei", "", 9)
    pdf.set_text_color(150)
    pdf.cell(0, 5, "—— 谢谢！——", align="C")


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    pdf = ProposalPDF()
    build(pdf)
    pdf.output(OUTPUT)
    print(f"PDF 已生成：{OUTPUT}")
    print(f"文件大小：{os.path.getsize(OUTPUT) / 1024:.1f} KB")
