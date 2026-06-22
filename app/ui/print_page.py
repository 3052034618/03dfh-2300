import os
import tempfile
from typing import List
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QFrame, QComboBox, QLineEdit, QCheckBox, QSplitter, QFileDialog,
    QGroupBox, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap

from .widgets import StatCard
from ..core.models import PriceItem, CategoryManager
from ..core.pdf_generator import PDFGenerator
from ..core.data_manager import ExcelImporter


def _has_pdf_support() -> bool:
    try:
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView
        return True
    except ImportError:
        return False


def _has_print_support() -> bool:
    try:
        from PySide6.QtPrintSupport import QPrinter, QPrintDialog
        return True
    except ImportError:
        return False


class PrintPage(QWidget):
    itemsUpdated = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_items: List[PriceItem] = []
        self._temp_pdf_path = None
        self._pdf_doc = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("打印与导出")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("生成 A4 打印版价目表、咨询师精简版，或导出 Excel/CSV 格式")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)

        left = QFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        settings_card = QFrame()
        settings_card.setObjectName("Card")
        s_layout = QVBoxLayout(settings_card)
        s_layout.setContentsMargins(15, 12, 15, 12)
        s_layout.setSpacing(10)

        s_layout.addWidget(QLabel("<b>📄 价目表标题</b>"))
        self.title_edit = QLineEdit("医美项目价目表")
        s_layout.addWidget(self.title_edit)

        s_layout.addWidget(QLabel("<b>📝 副标题/门店信息</b>"))
        self.subtitle_edit = QLineEdit()
        self.subtitle_edit.setPlaceholderText("如：XX医美 · 2025年版 · 最终解释权归本店所有")
        s_layout.addWidget(self.subtitle_edit)

        s_layout.addWidget(QLabel("<b>🎯 导出类型</b>"))
        self.export_type = QComboBox()
        self.export_type.addItem("A4 正式版价目表（客户用）", "a4_full")
        self.export_type.addItem("A4 标准版（不含会员价）", "a4_no_member")
        self.export_type.addItem("咨询师精简版", "consultant")
        s_layout.addWidget(self.export_type)

        cat_group = QGroupBox("📂 分类筛选")
        cat_layout = QVBoxLayout(cat_group)
        self.chk_cats = {}
        for cat in CategoryManager.get_all_categories():
            chk = QCheckBox(cat)
            chk.setChecked(True)
            self.chk_cats[cat] = chk
            cat_layout.addWidget(chk)
        s_layout.addWidget(cat_group)

        opt_group = QGroupBox("⚙️ 显示选项")
        opt_layout = QVBoxLayout(opt_group)
        self.chk_zero_price = QCheckBox("隐藏价格为 0 的项目")
        self.chk_zero_price.setChecked(True)
        self.chk_remark = QCheckBox("显示备注信息")
        self.chk_remark.setChecked(True)
        self.chk_sort_price = QCheckBox("按价格从高到低排序")
        opt_layout.addWidget(self.chk_zero_price)
        opt_layout.addWidget(self.chk_remark)
        opt_layout.addWidget(self.chk_sort_price)
        s_layout.addWidget(opt_group)

        btn_row = QHBoxLayout()
        self.btn_preview = QPushButton("🔍 预览PDF")
        self.btn_preview.setObjectName("PrimaryButton")
        self.btn_print = QPushButton("🖨️ 打印")
        btn_row.addWidget(self.btn_preview)
        btn_row.addWidget(self.btn_print)
        s_layout.addLayout(btn_row)

        export_group = QGroupBox("💾 导出到文件")
        export_layout = QGridLayout(export_group)
        self.btn_export_pdf = QPushButton("导出 PDF")
        self.btn_export_pdf.setObjectName("PrimaryButton")
        self.btn_export_excel = QPushButton("导出 Excel 完整版")
        self.btn_export_simple = QPushButton("导出 Excel 精简版")
        self.btn_export_csv = QPushButton("导出咨询师 CSV")
        export_layout.addWidget(self.btn_export_pdf, 0, 0)
        export_layout.addWidget(self.btn_export_excel, 0, 1)
        export_layout.addWidget(self.btn_export_simple, 1, 0)
        export_layout.addWidget(self.btn_export_csv, 1, 1)
        s_layout.addWidget(export_group)

        left_layout.addWidget(settings_card)

        stats_row = QHBoxLayout()
        self.stat_display = StatCard("展示项目数", "0", "#3b82f6")
        self.stat_cats_used = StatCard("使用分类", "0", "#10b981")
        self.stat_total_amount = StatCard("原价合计", "¥0", "#f59e0b")
        stats_row.addWidget(self.stat_display)
        stats_row.addWidget(self.stat_cats_used)
        stats_row.addWidget(self.stat_total_amount)
        left_layout.addLayout(stats_row)

        splitter.addWidget(left)

        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        preview_title = QLabel("<b>项目列表预览</b>")
        right_layout.addWidget(preview_title)

        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self.preview_table, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([400, 700])

        layout.addWidget(splitter, 1)

        self.btn_preview.clicked.connect(self._generate_and_preview)
        self.btn_print.clicked.connect(self._do_print)
        self.btn_export_pdf.clicked.connect(self._export_pdf)
        self.btn_export_excel.clicked.connect(lambda: self._export_excel(full=True))
        self.btn_export_simple.clicked.connect(lambda: self._export_excel(full=False))
        self.btn_export_csv.clicked.connect(self._export_csv)

        for chk in self.chk_cats.values():
            chk.stateChanged.connect(self._refresh_preview)
        self.chk_zero_price.stateChanged.connect(self._refresh_preview)
        self.chk_sort_price.stateChanged.connect(self._refresh_preview)
        self.export_type.currentIndexChanged.connect(self._refresh_preview)

    def set_items(self, items: List[PriceItem]):
        self.current_items = items
        self._refresh_preview()

    def _get_filtered_items(self) -> List[PriceItem]:
        active_cats = [cat for cat, chk in self.chk_cats.items() if chk.isChecked()]
        filtered = [it for it in self.current_items if it.category in active_cats]

        if self.chk_zero_price.isChecked():
            filtered = [it for it in filtered if it.original_price > 0 or it.member_price > 0]

        exp_type = self.export_type.currentData()
        if exp_type == "consultant":
            filtered = [it for it in filtered if it.original_price > 0]

        if self.chk_sort_price.isChecked():
            filtered.sort(key=lambda x: -max(x.original_price, x.member_price))
        else:
            cat_order = {c: i for i, c in enumerate(CategoryManager.get_all_categories())}
            filtered.sort(key=lambda x: (cat_order.get(x.category, 99), x.name))

        return filtered

    def _refresh_preview(self):
        items = self._get_filtered_items()
        exp_type = self.export_type.currentData()

        if exp_type == "consultant":
            headers = ["项目", "类别", "原价", "会员价", "底价"]
            self.preview_table.setColumnCount(len(headers))
            self.preview_table.setHorizontalHeaderLabels(headers)
            self.preview_table.setRowCount(len(items))
            for row, it in enumerate(items):
                name = it.display_name or it.name
                if len(name) > 18:
                    name = name[:18] + "..."
                values = [
                    name, it.category or "-",
                    f"¥{it.original_price:,.0f}" if it.original_price > 0 else "-",
                    f"¥{it.member_price:,.0f}" if it.member_price > 0 else "-",
                    f"¥{it.total_cost:,.0f}" if it.total_cost > 0 else "-"
                ]
                for col, val in enumerate(values):
                    cell = QTableWidgetItem(val)
                    if col >= 2:
                        cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    self.preview_table.setItem(row, col, cell)
        else:
            include_member = exp_type != "a4_no_member"
            if include_member:
                headers = ["项目名称", "分类", "原价", "会员价", "备注"]
            else:
                headers = ["项目名称", "分类", "价格", "备注"]
            self.preview_table.setColumnCount(len(headers))
            self.preview_table.setHorizontalHeaderLabels(headers)
            self.preview_table.setRowCount(len(items))
            for row, it in enumerate(items):
                if include_member:
                    values = [
                        it.display_name or it.name, it.category or "-",
                        f"¥{it.original_price:,.2f}" if it.original_price > 0 else "-",
                        f"¥{it.member_price:,.2f}" if it.member_price > 0 else "-",
                        it.remark or "-" if self.chk_remark.isChecked() else ""
                    ]
                else:
                    values = [
                        it.display_name or it.name, it.category or "-",
                        f"¥{it.original_price:,.2f}" if it.original_price > 0 else "-",
                        it.remark or "-" if self.chk_remark.isChecked() else ""
                    ]
                for col, val in enumerate(values):
                    cell = QTableWidgetItem(val)
                    if col >= 2:
                        cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    self.preview_table.setItem(row, col, cell)

        for col in range(self.preview_table.columnCount()):
            self.preview_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self.stat_display.update_value(str(len(items)))
        cats_used = set(it.category for it in items)
        self.stat_cats_used.update_value(str(len(cats_used)))
        total = sum(it.original_price for it in items)
        self.stat_total_amount.update_value(f"¥{total:,.0f}")

    def _prepare_temp_pdf(self) -> str:
        items = self._get_filtered_items()
        if not items:
            QMessageBox.warning(self, "提示", "没有可导出的项目")
            return ""

        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_path = os.path.join(temp_dir, f"price_preview_{timestamp}.pdf")

        exp_type = self.export_type.currentData()
        title = self.title_edit.text().strip() or "价目表"
        subtitle = self.subtitle_edit.text().strip()

        try:
            if exp_type == "consultant":
                PDFGenerator.generate_consultant_list(items, pdf_path, title=title)
            else:
                include_member = exp_type != "a4_no_member"
                PDFGenerator.generate_a4_price_list(items, pdf_path,
                                                   title=title, subtitle=subtitle,
                                                   include_member=include_member)
            return pdf_path
        except Exception as e:
            QMessageBox.critical(self, "生成失败", f"PDF生成失败：{str(e)}")
            return ""

    def _generate_and_preview(self):
        pdf_path = self._prepare_temp_pdf()
        if not pdf_path:
            return

        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView

            dialog = QMessageBox(self)
            dialog.setWindowTitle("PDF 已生成")
            dialog.setText(f"PDF 已成功生成！\n\n路径：{pdf_path}\n\n请使用系统默认PDF阅读器打开，或使用下方功能导出。")
            dialog.setIcon(QMessageBox.Information)
            open_btn = dialog.addButton("📂 打开文件夹", QMessageBox.ActionRole)
            view_btn = dialog.addButton("📖 打开文件", QMessageBox.ActionRole)
            ok_btn = dialog.addButton("确定", QMessageBox.AcceptRole)
            dialog.exec()

            clicked = dialog.clickedButton()
            if clicked == open_btn:
                folder = os.path.dirname(pdf_path)
                os.startfile(folder) if hasattr(os, "startfile") else None
            elif clicked == view_btn:
                os.startfile(pdf_path) if hasattr(os, "startfile") else None
        except Exception as e:
            QMessageBox.information(self, "完成", f"PDF 已生成：\n{pdf_path}")

    def _do_print(self):
        pdf_path = self._prepare_temp_pdf()
        if not pdf_path:
            return

        try:
            os.startfile(pdf_path, "print") if hasattr(os, "startfile") else None
            QMessageBox.information(self, "已发送打印", "打印任务已发送到系统打印队列\n（将使用默认 PDF 阅读器的打印功能）")
        except Exception as e:
            QMessageBox.critical(self, "打印失败", f"打印操作失败：{str(e)}")

    def _export_pdf(self):
        items = self._get_filtered_items()
        if not items:
            QMessageBox.warning(self, "提示", "没有可导出的项目")
            return

        default_name = f"{self.title_edit.text().strip() or '价目表'}_{datetime.now().strftime('%Y%m%d')}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出 PDF", default_name, "PDF 文件 (*.pdf)"
        )
        if not file_path:
            return

        exp_type = self.export_type.currentData()
        title = self.title_edit.text().strip() or "价目表"
        subtitle = self.subtitle_edit.text().strip()

        try:
            if exp_type == "consultant":
                PDFGenerator.generate_consultant_list(items, file_path, title=title)
            else:
                include_member = exp_type != "a4_no_member"
                PDFGenerator.generate_a4_price_list(items, file_path,
                                                   title=title, subtitle=subtitle,
                                                   include_member=include_member)
            QMessageBox.information(self, "导出成功", f"PDF 已保存到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败：{str(e)}")

    def _export_excel(self, full: bool):
        items = self._get_filtered_items()
        if not items:
            QMessageBox.warning(self, "提示", "没有可导出的项目")
            return

        suffix = "完整版" if full else "精简版"
        default_name = f"{self.title_edit.text().strip() or '价目表'}_{suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, f"导出 Excel {suffix}", default_name, "Excel 文件 (*.xlsx)"
        )
        if not file_path:
            return

        try:
            ExcelImporter.export_items(items, file_path, include_internal=full)
            QMessageBox.information(self, "导出成功", f"Excel 已保存到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败：{str(e)}")

    def _export_csv(self):
        items = self._get_filtered_items()
        if not items:
            QMessageBox.warning(self, "提示", "没有可导出的项目")
            return

        default_name = f"咨询师价目表_{datetime.now().strftime('%Y%m%d')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出咨询师 CSV", default_name, "CSV 文件 (*.csv)"
        )
        if not file_path:
            return

        try:
            PDFGenerator.generate_csv_consultant_list(items, file_path)
            QMessageBox.information(self, "导出成功", f"CSV 已保存到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败：{str(e)}")
