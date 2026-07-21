#!/usr/bin/env python3
"""生成用于 Common Agent RAGFlow 召回质量验收的多页 PDF 和 DOCX。"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPOSITORY_ROOT / "test-data" / "knowledge-base" / "corpus"
FONT_NAME = "Sarasa UI SC"


SECURITY_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "1. 适用范围与数据分级",
        (
            "本手册适用于北极星计划的平台元数据、知识内容、会话、工作流和审计记录。公开级数据可对外发布；内部级数据只能在项目成员之间共享；机密级数据只允许经授权岗位访问；受限级数据包含凭据、跨租户标识、未脱敏个人信息和安全取证材料。",
            "受限级数据不得进入普通工单、聊天群、模型提示词或前端日志。机密级资料可以进入获准的租户知识库，但必须保留来源、权限和删除记录。数据级别由资料所有者提出，安全负责人确认；无法判断时按更高一级处理。",
            "文档标题中出现“公开”不自动改变级别，必须以平台登记的分类为准。模型生成的摘要继承其最高来源级别，不能因为摘要更短就降低分类。",
        ),
    ),
    (
        "2. 身份、访问与加密",
        (
            "生产访问采用最小权限。Owner 管理租户与高风险配置，Editor 维护授权范围内的知识、员工和工作流，Viewer 只能读取与使用。跨租户资源 ID 即使格式合法也必须返回拒绝，不能通过错误差异确认资源是否存在。",
            "API Key 只保存在后端受控配置，不进入浏览器、普通日志、审计元数据或知识文档。传输使用 TLS，备份使用 AES-256-GCM 认证加密。恢复密钥与备份文件分开保管，任何单一保管人不能同时取得两者。",
            "登录会话撤销后必须立即失效。服务间请求使用独立凭据，不能复用用户 Cookie。紧急访问最长开放 60 分钟，到期自动收回，并在下一个工作日由安全负责人复核。",
        ),
    ),
    (
        "3. 安全事件响应",
        (
            "疑似泄漏、越权或凭据暴露后，发现人应在 10 分钟内通知安全值班组。主事件频道代号为 SEC-ALPHA；普通业务群只能发布脱敏状态，不得粘贴请求正文。值班组先冻结相关访问，再保存请求 ID、时间范围、操作者和脱敏轨迹。",
            "确认跨租户泄漏属于 P0。仅引用缺失且未发现越权时按运维影响定级，通常是 P1。安全定级可以高于服务定级。对外沟通由事件负责人统一发布，工程师不得自行承诺影响范围或删除证据。",
            "事件关闭前要验证凭据轮换、访问撤销、受影响租户通知、审计链连续和补救任务。临时缓解不等于关闭；若根因仍未修复，状态只能是已缓解。",
        ),
    ),
    (
        "4. 备份与灾难恢复目标",
        (
            "平台 MySQL 的目标为 RPO 24 小时、RTO 120 分钟；知识库文档内容同样采用 RPO 24 小时、RTO 120 分钟。订单索引属于单独的数据域，目标更严格，为 RPO 15 分钟、RTO 60 分钟。会话流式事件允许从持久摘要重建，不单独承诺零丢失。",
            "2027 年 2 月的草案曾把知识内容写成 RPO 12 小时、RTO 90 分钟，该值在容量演练后被废止。2027 年 3 月 1 日生效的正式值是 RPO 24 小时、RTO 120 分钟。检索回答必须采用正式值，并在用户询问旧值时说明其已废止。",
            "恢复完成不能只看容器健康。必须从正式页面登录，验证租户、模型配置、知识库、数字员工、历史会话、工作流和审计链；还要执行已知事实、跨文档和无答案三类检索。任何租户归属不一致都视为恢复失败。",
        ),
    ),
    (
        "5. 第三方、例外与审计",
        (
            "阿里百炼和 RAGFlow 是获准依赖，但获准不表示可以发送任意数据。模型请求只包含完成当前任务所需的最小上下文，受限级数据默认禁止出站。新增第三方必须记录地区、数据用途、保留、删除、失败语义和退出方案。",
            "安全例外必须包含申请人、业务理由、影响范围、补偿控制和到期时间。没有到期时间的例外无效。到期前未续期则自动恢复正式规则。例外不能取消租户隔离、凭据脱敏或审计记录。",
            "本手册的唯一检索标记是 SEC-LANTERN-582。它用于确认安全与连续性手册被召回；回答服务故障首次响应时间时应引用运维手册，而不是根据本手册的安全通知时限推断。",
        ),
    ),
)


ACCEPTANCE_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "1. 项目背景与部署范围",
        (
            "北辰咖啡是北极星计划的首个验收客户。本轮实际验收杭州和苏州共 12 家门店，每城 6 家，部署 36 台门店终端。产品蓝图中的首批规划是杭州、苏州、宁波共 18 家；宁波 6 家在观察期后再扩容，因此规划数和本次验收数并不矛盾。",
            "试运行开始于 2027 年 5 月 20 日，业务验收会议在 2027 年 6 月 2 日举行，正式上线日期为 2027 年 6 月 9 日。项目经理是周禾，业务验收负责人是顾宁，知识运营负责人是沈清。",
            "门店使用统一 Web 入口，不安装桌面客户端。终端仅保存短期会话 Cookie，不落地知识文档或模型凭据。门店离线时显示不可用，不用本地旧答案冒充在线检索结果。",
        ),
    ),
    (
        "2. 语料与测试方法",
        (
            "验收知识库包含 146 份制度、92 份运营公告和 38 份设备指引，共 276 份有效文档。知识团队准备 320 个问题，其中精确事实 120 个、语义改写 80 个、跨文档 70 个、冲突消解 30 个、无答案 20 个。问题在评测前冻结，实施团队不能通过修改问题迁就结果。",
            "检索指标使用 Top-5 命中率，要求相关来源至少有一个进入前五。回答指标单独计算引用可追溯率，要求引用能够回到正确文档和相关片段。模型措辞不同不直接判错，但数字、日期、角色和正式规则必须与标准答案一致。",
            "每类问题至少由两名评审独立打分，分歧由顾宁裁决。无答案问题若编造具体金额、人员或能力，直接记为失败；仅回答“资料不足”且指出缺少哪类信息才算通过。",
        ),
    ),
    (
        "3. 验收结果与性能",
        (
            "最终 Top-5 检索命中率为 92.4%，高于 90% 门槛；引用可追溯率为 98.0%，高于 97% 门槛。92.4% 不是引用率，98.0% 也不是答案准确率。跨文档问题完整回答率为 88.6%，无答案拒答正确率为 95.0%。",
            "常规问答端到端 P50 为 1.4 秒，P95 为 2.8 秒，低于产品蓝图 3.5 秒门槛。包含三份以上来源的跨文档问题 P95 为 4.6 秒，作为单独观察指标，不与常规问答门槛混用。连续 60 分钟运行未出现 Worker 重启或 RAGFlow OOM。",
            "36 台终端同时发起首轮问答时，成功率为 100%；第二轮追问成功率为 99.7%，一条请求因门店网络中断失败，重试后成功。审计抽样 50 条，租户、操作者、资源和结果字段完整，正文未进入审计元数据。",
        ),
    ),
    (
        "4. 缺陷、范围外事项与结论",
        (
            "验收保留两个非阻断问题：较长 PDF 首次解析时间波动较大；历史会话标题仅取第一条消息，暂不支持用户重命名。两项均不影响事实召回和引用，分别进入 2027 年 6 月与 7 月迭代。",
            "支付结算、会员积分写入、自动采购、排班决策和硬件远程控制不在本次范围。验收通过不能被解释为平台具备微信退款或远程重启咖啡机能力。需要这些能力时必须重新做产品和安全评审。",
            "结论为有条件通过：12 家门店于 2027 年 6 月 9 日上线，观察期 14 天；剩余宁波 6 家在观察期无 P0/P1 且行动项完成后扩容。本记录的唯一检索标记是 ACC-HARBOR-946。",
        ),
    ),
)


def _set_docx_run(
    run, *, size: float, bold: bool = False, color: str = "222222"
) -> None:
    run.font.name = FONT_NAME
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for key in ("eastAsia", "ascii", "hAnsi"):
        fonts.set(qn(f"w:{key}"), FONT_NAME)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _configure_docx(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.9)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(0.85)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.45)
    section.footer_distance = Inches(0.45)

    normal = document.styles["Normal"]
    normal.font.name = FONT_NAME
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.25
    for style_name, size, before, after, color in (
        ("Heading 1", 16, 18, 10, "2E74B5"),
        ("Heading 2", 13, 14, 7, "1F4D78"),
    ):
        style = document.styles[style_name]
        style.font.name = FONT_NAME
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _set_docx_run(
        header.add_run("北辰咖啡试点验收记录 | 虚构测试资料"), size=9, color="666666"
    )
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _set_docx_run(
        footer.add_run("Common Agent Knowledge Fixture"), size=9, color="777777"
    )


def generate_docx() -> None:
    document = Document()
    _configure_docx(document)
    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(5)
    _set_docx_run(
        title.add_run("北辰咖啡试点验收记录"), size=25, bold=True, color="0B2545"
    )
    subtitle = document.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(14)
    _set_docx_run(
        subtitle.add_run("文档编号 NP-ACC-2027-06 | 正式版 1.0 | 全部信息均为虚构"),
        size=10.5,
        color="555555",
    )

    for index, (heading, paragraphs) in enumerate(ACCEPTANCE_SECTIONS):
        if index:
            document.add_page_break()
        document.add_heading(heading, level=1)
        for content in paragraphs:
            document.add_paragraph(content)
        if index == 1:
            document.add_heading("评分边界", level=2)
            document.add_paragraph(
                "评测只使用冻结问题和正式知识库。直接查看源文件、把标准答案放入系统提示词、使用"
                "Mock 检索或只校验日志都不算用户路径验收。"
            )
        if index == 2:
            document.add_heading("失败定位", level=2)
            document.add_paragraph(
                "未召回正确文档属于检索失败；文档已召回但回答混淆数字属于生成失败；引用指向错误"
                "租户属于安全失败。三类问题必须分别记录，不能只用总分掩盖。"
            )

    document.core_properties.title = "北辰咖啡试点验收记录（虚构测试资料）"
    document.core_properties.subject = "Common Agent RAGFlow DOCX 召回测试"
    document.core_properties.author = "Common Agent Test Fixture"
    document.core_properties.keywords = "fictional,ragflow,retrieval,acceptance"
    document.save(OUTPUT_DIR / "04-pilot-acceptance.docx")


def _pdf_page(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("STSong-Light", 8.5)
    canvas.setFillColor(HexColor("#777777"))
    canvas.drawString(inch, 0.45 * inch, "北极星安全与连续性手册 | 虚构测试资料")
    canvas.drawRightString(7.5 * inch, 0.45 * inch, f"第 {document.page} 页")
    canvas.restoreState()


def generate_pdf() -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "ZhTitle",
        parent=base["Title"],
        fontName="STSong-Light",
        fontSize=23,
        leading=31,
        textColor=HexColor("#0B2545"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "ZhSubtitle",
        parent=base["Normal"],
        fontName="STSong-Light",
        fontSize=10,
        leading=16,
        textColor=HexColor("#666666"),
        alignment=TA_CENTER,
        spaceAfter=20,
    )
    heading = ParagraphStyle(
        "ZhHeading",
        parent=base["Heading2"],
        fontName="STSong-Light",
        fontSize=15,
        leading=22,
        textColor=HexColor("#2E74B5"),
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    body = ParagraphStyle(
        "ZhBody",
        parent=base["BodyText"],
        fontName="STSong-Light",
        fontSize=11,
        leading=20,
        firstLineIndent=22,
        textColor=HexColor("#222222"),
        alignment=TA_LEFT,
        spaceAfter=12,
    )
    pdf = SimpleDocTemplate(
        str(OUTPUT_DIR / "03-security-and-continuity.pdf"),
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=0.8 * inch,
        bottomMargin=0.7 * inch,
        title="北极星安全与连续性手册（虚构测试资料）",
        author="Common Agent Test Fixture",
        subject="Common Agent RAGFlow PDF 召回测试",
    )
    story = [
        Paragraph("北极星安全与连续性手册", title),
        Paragraph("文档编号 NP-SEC-2027-03 | 正式版 2.0 | 2027-03-01 生效", subtitle),
    ]
    for index, (section_title, paragraphs) in enumerate(SECURITY_SECTIONS):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(section_title, heading))
        for content in paragraphs:
            story.append(Paragraph(content, body))
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                "章节检查提示：区分正式规则、旧版值、服务运维目标与安全恢复目标。",
                subtitle,
            )
        )
    pdf.build(story, onFirstPage=_pdf_page, onLaterPages=_pdf_page)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_pdf()
    generate_docx()
    print(f"RAGFlow 召回质量样本已生成：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
