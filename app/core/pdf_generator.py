import os
from typing import List, Dict, Optional
from collections import defaultdict
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from .models import PriceItem


def _register_chinese_font():
    font_names = []
    font_paths = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttf"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simsun.ttc"),
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simhei.ttf"),
    ]
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_name = f"ChineseFont_{len(font_names)}"
                subfontIndex = 0 if font_path.endswith(".ttc") else None
                if subfontIndex is not None:
                    pdfmetrics.registerFont(TTFont(font_name, font_path, subfontIndex=subfontIndex))
                else:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                font_names.append(font_name)
            except Exception:
                continue
    return font_names[0] if font_names else "Helvetica"


CHINESE_FONT = None


def get_font():
    global CHINESE_FONT
    if CHINESE_FONT is None:
        CHINESE_FONT = _register_chinese_font()
    return CHINESE_FONT


class PDFGenerator:
    @staticmethod
    def _get_styles():
        styles = getSampleStyleSheet()
        font = get_font()

        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Title"],
            fontName=font,
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=12,
            textColor=colors.HexColor("#1a1a2e")
        )

        subtitle_style = ParagraphStyle(
            "CustomSubtitle",
            parent=styles["Normal"],
            fontName=font,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            spaceAfter=18,
            textColor=colors.HexColor("#666666")
        )

        category_style = ParagraphStyle(
            "CategoryTitle",
            parent=styles["Heading2"],
            fontName=font,
            fontSize=13,
            leading=17,
            spaceBefore=10,
            spaceAfter=8,
            textColor=colors.HexColor("#ffffff"),
            backColor=colors.HexColor("#4472C4"),
            borderPadding=(4, 8, 4, 8)
        )

        normal_style = ParagraphStyle(
            "CustomNormal",
            parent=styles["Normal"],
            fontName=font,
            fontSize=10,
            leading=14,
        )

        header_style = ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName=font,
            fontSize=10,
            leading=13,
            textColor=colors.white,
            alignment=TA_CENTER
        )

        cell_style = ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName=font,
            fontSize=9,
            leading=12,
        )

        price_style = ParagraphStyle(
            "TableCellRight",
            parent=cell_style,
            alignment=TA_RIGHT,
        )

        return {
            "title": title_style,
            "subtitle": subtitle_style,
            "category": category_style,
            "normal": normal_style,
            "header": header_style,
            "cell": cell_style,
            "price": price_style
        }

    @staticmethod
    def generate_a4_price_list(items: List[PriceItem], output_path: str,
                               title: str = "医美项目价目表",
                               subtitle: str = "",
                               include_member: bool = True) -> str:
        styles = PDFGenerator._get_styles()
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=18 * mm
        )

        elements = []
        elements.append(Paragraph(title, styles["title"]))
        if subtitle:
            elements.append(Paragraph(subtitle, styles["subtitle"]))

        categorized = defaultdict(list)
        for item in items:
            categorized[item.category or "其他"].append(item)

        category_order = ["光电类", "注射类", "手术类", "清洁补水", "皮肤护理", "其他"]
        sorted_categories = sorted(
            categorized.keys(),
            key=lambda x: category_order.index(x) if x in category_order else 99
        )

        for category in sorted_categories:
            category_items = categorized[category]
            if not category_items:
                continue

            elements.append(Paragraph(f"■ {category}", styles["category"]))

            table_data = []
            if include_member:
                headers = ["项目名称", "原价", "会员价", "备注"]
                col_widths = [85 * mm, 25 * mm, 25 * mm, 55 * mm]
            else:
                headers = ["项目名称", "价格", "备注"]
                col_widths = [85 * mm, 30 * mm, 75 * mm]

            table_data.append([Paragraph(h, styles["header"]) for h in headers])

            for item in category_items:
                display_name = item.display_name or item.name
                name_p = Paragraph(display_name, styles["cell"])
                remark_p = Paragraph(item.remark or "-", styles["cell"])

                if include_member:
                    orig_p = Paragraph(
                        f"¥{item.original_price:,.2f}" if item.original_price > 0 else "-",
                        styles["price"]
                    )
                    mem_p = Paragraph(
                        f"¥{item.member_price:,.2f}" if item.member_price > 0 else "-",
                        styles["price"]
                    )
                    table_data.append([name_p, orig_p, mem_p, remark_p])
                else:
                    price_p = Paragraph(
                        f"¥{item.original_price:,.2f}" if item.original_price > 0 else "-",
                        styles["price"]
                    )
                    table_data.append([name_p, price_p, remark_p])

            table = Table(table_data, colWidths=col_widths, repeatRows=1)
            table_style = TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 1), (-2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#f8f9fa")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
            table.setStyle(table_style)

            elements.append(KeepTogether([table, Spacer(1, 6 * mm)]))

        doc.build(elements)
        return output_path

    @staticmethod
    def generate_consultant_list(items: List[PriceItem], output_path: str,
                                  title: str = "咨询师精简价目表") -> str:
        styles = PDFGenerator._get_styles()
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm
        )

        elements = []
        elements.append(Paragraph(title, styles["title"]))
        elements.append(Spacer(1, 4 * mm))

        table_data = []
        headers = ["项目", "类别", "原价", "会员价", "底价"]
        col_widths = [55 * mm, 25 * mm, 25 * mm, 25 * mm, 25 * mm]

        table_data.append([Paragraph(h, styles["header"]) for h in headers])

        for item in sorted(items, key=lambda x: (x.category, x.name)):
            display_name = item.display_name or item.name
            if len(display_name) > 12:
                display_name = display_name[:12] + "..."

            table_data.append([
                Paragraph(display_name, styles["cell"]),
                Paragraph(item.category or "-", styles["cell"]),
                Paragraph(f"¥{item.original_price:,.0f}" if item.original_price > 0 else "-", styles["price"]),
                Paragraph(f"¥{item.member_price:,.0f}" if item.member_price > 0 else "-", styles["price"]),
                Paragraph(f"¥{item.total_cost:,.0f}" if item.total_cost > 0 else "-", styles["price"]),
            ])

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f1faee")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ])
        table.setStyle(table_style)
        elements.append(table)

        doc.build(elements)
        return output_path

    @staticmethod
    def generate_csv_consultant_list(items: List[PriceItem], output_path: str) -> str:
        import csv
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["项目名称", "前台展示名", "分类", "原价", "会员价",
                           "医生费", "耗材费", "耗材品牌", "成本价", "底价", "备注"])
            for item in sorted(items, key=lambda x: (x.category, x.name)):
                writer.writerow([
                    item.name,
                    item.display_name or item.name,
                    item.category,
                    item.original_price,
                    item.member_price,
                    item.doctor_fee,
                    item.material_fee,
                    item.material_brand,
                    item.cost_price,
                    item.total_cost,
                    item.remark
                ])
        return output_path
