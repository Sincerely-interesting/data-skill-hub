"""
PDF 报告生成器 — 素材内容分析报告（Platypus 自动排版版）

基于 reportlab Platypus 框架（SimpleDocTemplate + Paragraph/Table），自动处理
分页、断行、溢出裁剪，杜绝 Canvas 手绘的页间重叠/空白页问题。

结构（对齐早期 generate_smb_report.py 风格）：
  1. 标题页 — 报告名称 + 时间
  2. 数据总览 — 5 张 KPI 卡（总数/图片/视频/有效标注/平均置信度）
  3. 标签分布 — 彩色统计表 + Unicode 条形图
  4. 分类代表素材 — 各标签置信度 TOP3 样本
  5. 图片/视频分类型统计
  6. 待人工复核清单 — 低置信度样本
  7. 素材明细列表（全部）— 全量编号/标签/信度/判定理由

用法：
    python run_pipeline.py report -c labeling_cache.json -o output.pdf
"""

from __future__ import annotations

import json
import sys
import time as _time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.platypus.frames import Frame

# ──────────────────── 中文字体注册 ────────────────────

import os
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
try:
    from loguru import logger as _rlog
except Exception:
    import logging as _rlogging
    _rlog = _rlogging.getLogger("reporter")

def _resolve_cjk_font():
    """跨平台探测一个可用的中文 TTF；返回路径或 None。"""
    if os.path.exists("C:/Windows/Fonts/msyh.ttc"):
        return "C:/Windows/Fonts/msyh.ttc"
    for _p in [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]:
        if os.path.exists(_p):
            return _p
    return None

_FONT_PATH = _resolve_cjk_font()
if _FONT_PATH:
    try:
        pdfmetrics.registerFont(TTFont("Msyh", _FONT_PATH))
        pdfmetrics.registerFont(TTFont("MsyhBd", _FONT_PATH))            # 粗体兜底用同字体
        pdfmetrics.registerFont(TTFont("MsyhNormal", _FONT_PATH, subfontIndex=0))
        FONT_CN = "Msyh"
        FONT_CN_BD = "MsyhBd"
    except Exception as _e:
        _rlog.warning(f"中文 TTF 注册失败，降级到内置 CID 字体: {_e}")
        _FONT_PATH = None

if not _FONT_PATH:
    # 兜底：reportlab 内置 STSong-Light 中文 CID 字体，跨平台无需字体文件
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        FONT_CN = "STSong-Light"
        FONT_CN_BD = "STSong-Light"
    except Exception as _e:
        _rlog.warning(f"兜底中文字体也失败，PDF 报表将用西文字体: {_e}")
        FONT_CN = "Helvetica"
        FONT_CN_BD = "Helvetica-Bold"

# ──────────────────── 配置常量 ────────────────────

LABEL_ORDERS = [
    "穿搭精选(核心)",
    "单品展示(上脚)",
    "性能测试",
    "静物展示",
    "明星穿搭",
    "创意静物",
    "其他",
    "穿搭精选(次要)",
]

LABEL_COLORS = {
    "穿搭精选(核心)": "#27AE60",
    "单品展示(上脚)": "#2980B9",
    "性能测试": "#E67E22",
    "静物展示": "#16A085",
    "明星穿搭": "#E74C3C",
    "创意静物": "#9B59B6",
    "其他": "#95A5A6",
    "穿搭精选(次要)": "#3498DB",
}

# 别名（短名称，用于表格和条形图显示）
LABEL_ALIAS = {
    "穿搭精选(核心)": "穿搭精选",
    "单品展示(上脚)": "单品上脚",
    "性能测试": "功能演示",
    "静物展示": "常规静物",
    "明星穿搭": "明星同款",
    "创意静物": "创意静物",
    "其他": "其他",
    "穿搭精选(次要)": "半身穿搭",
}

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm


# ──────────────────── 样式定义 ────────────────────

def _styles() -> dict:
    """返回全部 ParagraphStyle 的命名字典。"""
    return {
        "title": ParagraphStyle(
            "TitleCN",
            fontName=FONT_CN_BD,
            fontSize=22,
            leading=30,
            spaceAfter=10,
            textColor=HexColor("#2C3E50"),
        ),
        "h1": ParagraphStyle(
            "H1CN",
            fontName=FONT_CN_BD,
            fontSize=16,
            leading=22,
            spaceAfter=8,
            spaceBefore=14,
            textColor=HexColor("#2C3E50"),
        ),
        "h2": ParagraphStyle(
            "H2CN",
            fontName=FONT_CN_BD,
            fontSize=13,
            leading=18,
            spaceAfter=6,
            spaceBefore=10,
            textColor=HexColor("#34495E"),
        ),
        "body": ParagraphStyle(
            "BodyCN",
            fontName=FONT_CN,
            fontSize=9,
            leading=14,
            spaceAfter=4,
            textColor=HexColor("#555555"),
        ),
        "stat_val": ParagraphStyle(
            "StatValCN",
            fontName=FONT_CN_BD,
            fontSize=26,
            leading=30,
            alignment=TA_CENTER,
            textColor=HexColor("#2C3E50"),
        ),
        "stat_lbl": ParagraphStyle(
            "StatLblCN",
            fontName=FONT_CN,
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            textColor=HexColor("#7F8C8D"),
        ),
        "th": ParagraphStyle(
            "THCN",
            fontName=FONT_CN_BD,
            fontSize=8,
            textColor=white,
            alignment=TA_CENTER,
            leading=12,
        ),
        "td": ParagraphStyle(
            "TDCN",
            fontName=FONT_CN,
            fontSize=8.5,
            leading=12,
            textColor=HexColor("#333333"),
        ),
        "td_sm": ParagraphStyle(
            "TDSmCN",
            fontName=FONT_CN,
            fontSize=8,
            leading=11,
            textColor=HexColor("#333333"),
        ),
        "review": ParagraphStyle(
            "ReviewCN",
            fontName=FONT_CN,
            fontSize=8,
            leading=11,
            textColor=HexColor("#C0392B"),
        ),
        "footer": ParagraphStyle(
            "FooterCN",
            fontName=FONT_CN,
            fontSize=7,
            textColor=HexColor("#AAAAAA"),
            alignment=TA_LEFT,
        ),
    }


STYLES = _styles()


class ReportGenerator:
    """从打标缓存 JSON 生成 PDF 分析报告。

    Parameters
    ----------
    cache_file : str | Path
        labeling_cache.json 路径。
    """

    def __init__(self, cache_file: str | Path):
        self.cache_file = Path(cache_file)
        self._data: Dict[str, Any] = {}

    # ────── 公开 API ──────

    def load(self) -> ReportGenerator:
        """加载缓存数据。"""
        if not self.cache_file.exists():
            raise FileNotFoundError(f"缓存文件不存在: {self.cache_file}")
        self._data = json.loads(self.cache_file.read_text("utf-8"))
        print(f"  素材数: {len(self._data)}")
        return self

    def generate(self, output_path: str | Path) -> Path:
        """生成 PDF 报告，返回输出文件路径。"""
        t0 = _time.time()
        self.load()

        out = Path(output_path)
        doc = SimpleDocTemplate(
            str(out),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=12 * mm,
            bottomMargin=16 * mm,
            title="电商素材智能分析报告",
            author="AI Labeler",
        )

        story = []

        # ① 标题
        story.extend(self._build_title())

        # ② 数据总览
        story.extend(self._build_summary())

        # ③ 标签分布（表+条形图）
        story.extend(self._build_label_distribution())

        # ④ 分类代表素材 TOP3
        story.extend(self._build_representatives())

        # ⑤ 图片/视频分类型统计
        story.extend(self._build_type_breakdown())

        # ⑥ 待人工复核清单
        story.extend(self._build_review_list())

        # ⑦ 全部明细表
        story.extend(self._build_detail_list())

        # ⑧ 页脚信息
        story.extend(self._build_footer())

        doc.build(story, onFirstPage=self._page_template, onLaterPages=self._page_template)

        elapsed = _time.time() - t0
        kb = out.stat().st_size / 1024
        print(f"\nSUCCESS: {out} ({kb:.0f} KB, {elapsed:.1f}s)")
        return out

    # ────── 页眉/脚模板 ──────

    @staticmethod
    def _page_template(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT_CN, 7)
        canvas.setFillColor(HexColor("#AAAAAA"))
        canvas.drawString(MARGIN, 8 * mm, "电商素材多模态智能识别 · 分析报告")
        canvas.drawRightString(PAGE_W - MARGIN, 8 * mm, f"{doc.page}")
        canvas.restoreState()

    # ────── ① 标题 ──────

    def _build_title(self) -> list:
        return [
            Spacer(1, 15),
            Paragraph("电商素材智能分析报告", STYLES["title"]),
            Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M"), STYLES["body"]),
            Spacer(1, 10),
        ]

    # ────── ② 数据总览 ──────

    def _build_summary(self) -> list:
        d = self._data
        total = len(d)
        images = sum(1 for v in d.values() if self._guess_type(v) == "image")
        videos = total - images
        labeled = sum(1 for v in d.values() if v.get("label", "").strip())
        avg_conf = sum(v.get("confidence", 0) for v in d.values()) / max(total, 1)

        vals = [str(total), str(images), str(videos), f"{labeled}/{total}", f"{avg_conf:.2f}"]
        labs = ["素材总数", "图片素材", "视频素材", "有效标注", "平均置信度"]

        row1 = [Paragraph(v, STYLES["stat_val"]) for v in vals]
        row2 = [Paragraph(l, STYLES["stat_lbl"]) for l in labs]

        cw = (PAGE_W - 2 * MARGIN) / 5
        tbl = Table([row1, row2], colWidths=[cw] * 5, hAlign="CENTER")
        tbl.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        img_conf = (
            sum(v.get("confidence", 0) for v in d.values() if self._guess_type(v) == "image") / max(images, 1)
            if images else 0
        )
        vid_conf = (
            sum(v.get("confidence", 0) for v in d.values() if self._guess_type(v) == "video") / max(videos, 1)
            if videos else 0
        )

        return [
            Paragraph("数据总览", STYLES["h1"]),
            tbl,
            Spacer(1, 6),
            Paragraph(
                f"图片素材平均置信度: {img_conf:.3f} | 视频素材平均置信度: {vid_conf:.3f}",
                STYLES["body"],
            ),
            Spacer(1, 10),
        ]

    # ────── ③ 标签分布 ──────

    def _build_label_distribution(self) -> list:
        d = self._data
        total = len(d)

        lc = Counter()
        img_lc = Counter()
        vid_lc = Counter()
        for v in d.values():
            lab = self._norm_label(v.get("label", ""))
            lc[lab] += 1
            t = self._guess_type(v)
            if t == "image":
                img_lc[lab] += 1
            elif t == "video":
                vid_lc[lab] += 1

        # ---- 表格 ----
        th_style = STYLES["th"]
        td_style = STYLES["td"]

        hdr = [
            Paragraph("标签", th_style),
            Paragraph("总计", th_style),
            Paragraph("占比", th_style),
            Paragraph("图片", th_style),
            Paragraph("视频", th_style),
        ]
        rows = [hdr]
        for label in LABEL_ORDERS:
            c = lc.get(label, 0)
            ic = img_lc.get(label, 0)
            vc = vid_lc.get(label, 0)
            pct = f"{c / total * 100:.1f}%"
            color = LABEL_COLORS.get(label, "#999")
            alias = LABEL_ALIAS.get(label, label)
            rows.append([
                Paragraph(f'<font color="{color}">■</font> {alias}', td_style),
                Paragraph(str(c), td_style),
                Paragraph(pct, td_style),
                Paragraph(str(ic), td_style),
                Paragraph(str(vc), td_style),
            ])

        usable = PAGE_W - 2 * MARGIN
        cw = [130, 50, 50, 50, 50]
        tbl = Table(rows, colWidths=[usable - sum(cw[1:])] + cw[1:])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2C3E50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#DDDDDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["#FFFFFF", "#F5F6FA"]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))

        # ---- Unicode 条形图 ----
        bars = []
        for label in LABEL_ORDERS:
            c = lc.get(label, 0)
            if c == 0:
                continue
            pct = c / total * 100
            bar_w = int(pct * 2.5)
            color = LABEL_COLORS.get(label, "#999")
            alias = LABEL_ALIAS.get(label, label)
            bars.append(Paragraph(
                f'<font size="9" face="{FONT_CN_BD}">{alias}</font>  '
                f'<font color="{color}" face="{FONT_CN}">{"█" * max(bar_w, 1)}</font>  '
                f'<font size="8" face="{FONT_CN}">{c}<super>个</super> ({pct:.1f}%)</font>',
                STYLES["body"],
            ))

        return [
            Paragraph("标签分布", STYLES["h1"]),
            tbl,
            Spacer(1, 8),
            *bars,
            Spacer(1, 10),
        ]

    # ────── ④ 分类代表素材 TOP3 ──────

    def _build_representatives(self) -> list:
        d = self._data
        by_label: Dict[str, list] = defaultdict(list)
        for mid, info in d.items():
            lab = info.get("label", "")
            conf = info.get("confidence", 0)
            reason = info.get("reasoning", "")
            mtype = self._guess_type(info)
            by_label[self._norm_label(lab)].append((conf, mid, mtype, reason))

        story = []
        story.append(Paragraph(
            "分类代表素材 （各标签置信度最高的样本）",
            STYLES["h1"],
        ))
        story.append(Paragraph(
            "下表列出每个标签分类中置信度最高的 2~3 个代表素材，可作为各类别的典型参考。",
            STYLES["body"],
        ))
        story.append(Spacer(1, 6))

        th_s = STYLES["th"]
        td_s = STYLES["td"]

        for label in LABEL_ORDERS:
            items = sorted(by_label.get(label, []), reverse=True)[:3]
            if not items:
                continue

            color = LABEL_COLORS.get(label, "#999")
            alias = LABEL_ALIAS.get(label, label)
            count = len(by_label[label])
            story.append(Paragraph(
                f'<font color="{color}" face="{FONT_CN_BD}" size="11">'
                f"■ {alias}</font>"
                f'<font face="{FONT_CN}" size="9">（共{count}个，置信度TOP{len(items)}）</font>',
                STYLES["h2"],
            ))

            rows = [[Paragraph("#", th_s), Paragraph("素材ID", th_s),
                    Paragraph("类", th_s), Paragraph("信度", th_s),
                    Paragraph("判定理由", th_s)]]
            for i, (conf, mid, mtype, reason) in enumerate(items):
                m = "图" if mtype == "image" else "视"
                rows.append([
                    Paragraph(str(i + 1), td_s),
                    Paragraph(mid, td_s),
                    Paragraph(m, td_s),
                    Paragraph(f"{conf:.2f}", td_s),
                    Paragraph((reason or "")[:60], td_s),
                ])

            usable = PAGE_W - 2 * MARGIN
            cw = [20, 80, 22, 36, usable - 158]
            tbl = Table(rows, colWidths=cw)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor(color)),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (3, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#E0E0E0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["#FFFFFF", "#F8F9FC"]),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 6))

        return story

    # ────── ⑤ 图片/视频分类型统计 ──────

    def _build_type_breakdown(self) -> list:
        d = self._data
        img_lc: Counter = Counter()
        vid_lc: Counter = Counter()
        for v in d.values():
            lab = self._norm_label(v.get("label", ""))
            t = self._guess_type(v)
            if t == "image":
                img_lc[lab] += 1
            elif t == "video":
                vid_lc[lab] += 1

        total_img = sum(img_lc.values())
        total_vid = sum(vid_lc.values())
        if not total_img and not total_vid:
            return []

        story = []
        story.append(Paragraph("图片/视频分类型统计", STYLES["h1"]))

        for title, labels_dict, total_n in [
            ("图片素材", img_lc, total_img),
            ("视频素材", vid_lc, total_vid),
        ]:
            if total_n == 0:
                continue
            story.append(Paragraph(f"<b>{title} ({total_n}个)</b>", STYLES["h2"]))
            for label in LABEL_ORDERS:
                c = labels_dict.get(label, 0)
                if c == 0:
                    continue
                pct = c / total_n * 100
                bar_w = int(pct * 2)
                color = LABEL_COLORS.get(label, "#999")
                alias = LABEL_ALIAS.get(label, label)
                story.append(Paragraph(
                    f'{alias}: {c}个 ({pct:.1f}%) '
                    f'<font color="{color}">{"▌" * max(bar_w, 1)}</font>',
                    STYLES["body"],
                ))
            story.append(Spacer(1, 6))

        return story

    # ────── ⑥ 待人工复核清单 ──────

    def _build_review_list(self, threshold: float = 0.91) -> list:
        d = self._data
        low_items = []
        for mid, info in d.items():
            conf = info.get("confidence", 0)
            if 0 < conf < threshold:
                low_items.append((
                    conf, mid,
                    self._norm_label(info.get("label", "")),
                    self._guess_type(info),
                    info.get("reasoning", ""),
                ))
        low_items.sort()

        story = []
        story.append(Paragraph("待人工复核清单", STYLES["h1"]))
        story.append(Paragraph(
            f"以下{threshold * 100:.0f}分以下素材 AI 判定置信度较低，建议人工复核确认标签准确性。",
            STYLES["body"],
        ))
        story.append(Spacer(1, 6))

        if not low_items:
            story.append(Paragraph("所有素材置信度均在安全线以上，无需复核。", STYLES["body"]))
            story.append(Spacer(1, 8))
            return story

        th_s = STYLES["th"]
        rev_mid = STYLES["review"]
        rev_low = ParagraphStyle(
            "RevLowCN",
            fontName=FONT_CN,
            fontSize=8,
            leading=11,
            textColor=HexColor("#7F8C8D"),
        )

        rows = [[Paragraph("#", th_s), Paragraph("素材ID", th_s),
                Paragraph("类", th_s), Paragraph("当前标签", th_s),
                Paragraph("信度", th_s), Paragraph("判定理由", th_s)]]

        for i, (conf, mid, label, mtype, reason) in enumerate(low_items):
            m = "图" if mtype == "image" else "视"
            alias = LABEL_ALIAS.get(label, label)
            rows.append([
                Paragraph(str(i + 1), rev_low),
                Paragraph(mid, rev_mid),
                Paragraph(m, rev_low),
                Paragraph(alias, rev_low),
                Paragraph(f"{conf:.2f}", rev_low),
                Paragraph((reason or "")[:55], rev_low),
            ])

        usable = PAGE_W - 2 * MARGIN
        fixed = 18 + 78 + 20 + 108 + 34
        cw = [18, 78, 20, 108, 34, usable - fixed]
        tbl = Table(rows, colWidths=cw)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#C0392B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (4, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#FADBD8")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["#FFF5F5", "#FDEDEC"]),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6))

        # 分布摘要
        dist = Counter(lbl for _, _, lbl, _, _ in low_items)
        parts = ", ".join(f"{LABEL_ALIAS.get(k, k)}: {v}个" for k, v in dist.most_common())
        story.append(Paragraph(f"待复核标签分布: {parts}", STYLES["body"]))
        story.append(Spacer(1, 6))
        return story

    # ────── ⑦ 全部明细表 ──────

    def _build_detail_list(self, page_size: int = 35) -> list:
        d = self._data
        sorted_items = sorted(
            d.items(), key=lambda x: x[1].get("confidence", 0), reverse=True,
        )
        total_items = len(sorted_items)
        total_pages = (total_items + page_size - 1) // page_size

        story = []
        story.append(Paragraph("素材明细列表（全部）", STYLES["h1"]))

        th_s = STYLES["th"]
        td_s = STYLES["td_sm"]

        for page in range(total_pages):
            start = page * page_size
            end = min(start + page_size, total_items)

            rows = [[Paragraph("#", th_s), Paragraph("素材ID", th_s),
                    Paragraph("类", th_s), Paragraph("标签", th_s),
                    Paragraph("信度", th_s), Paragraph("判定理由", th_s)]]

            for i, (mid, info) in enumerate(sorted_items[start:end]):
                idx = i + start + 1
                label = self._norm_label(info.get("label", ""))
                mtype = self._guess_type(info)
                mtype_short = "图" if mtype == "image" else "视"
                conf = info.get("confidence", 0)
                reason = (info.get("reasoning", "") or "")[:50]
                alias = LABEL_ALIAS.get(label, label)

                rows.append([
                    Paragraph(str(idx), td_s),
                    Paragraph(mid, td_s),
                    Paragraph(mtype_short, td_s),
                    Paragraph(alias, td_s),
                    Paragraph(f"{conf:.2f}", td_s),
                    Paragraph(reason, td_s),
                ])

            usable = PAGE_W - 2 * MARGIN
            fixed_cols = 28 + 82 + 22 + 110 + 38
            cw = [28, 82, 22, 110, 38, usable - fixed_cols]
            tbl = Table(rows, colWidths=cw)
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2C3E50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (4, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#EEEEEE")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["#FFFFFF", "#F8F9FC"]),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 6))

        story.append(Spacer(1, 6))
        return story

    # ────── ⑧ 页脚信息 ──────

    @staticmethod
    def _build_footer() -> list:
        return [
            Spacer(1, 15),
            Paragraph("—" * 50, STYLES["body"]),
            Paragraph(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", STYLES["body"]),
            Paragraph(f"数据来源: {Path(__file__).parent.name}", STYLES["body"]),
        ]

    # ────── 辅助方法 ──────

    @staticmethod
    def _norm_label(raw: str) -> str:
        """将原始标签归一化到 LABEL_ORDERS 中的标准名。"""
        s = raw.strip()
        if s in LABEL_ORDERS:
            return s
        for order_name in LABEL_ORDERS:
            if order_name in s or s in order_name:
                return order_name
        return "其他"

    @staticmethod
    def _guess_type(info: dict) -> str:
        """根据 material_id 或上下文推断素材类型（缓存无 type 字段时的回退）。"""
        # 尝试从 reasoning 中推断
        reasoning = (info.get("reasoning") or "").lower()
        if "视频" in reasoning or "mp4" in reasoning or "mov" in reasoning:
            return "video"
        if "图片" in reasoning or "jpg" in reasoning or "png" in reasoning:
            return "image"
        # 尝试从 material_id 所在目录推断（如果路径可访问）
        mid = info.get("material_id", "")
        # 默认：长 ID 更可能是视频目录（经验规则，非绝对准确）
        return "image"


# ────── CLI 入口 ──────

def main():
    """独立运行入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="生成素材分析 PDF 报告")
    parser.add_argument("--cache-file", "-c", required=True, help="labeling_cache.json 路径")
    parser.add_argument("--output", "-o", default="素材分析报告.pdf", help="输出 PDF 路径")
    args = parser.parse_args()

    gen = ReportGenerator(args.cache_file)
    out = gen.generate(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
