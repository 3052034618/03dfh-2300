from typing import List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QDialog, QDialogButtonBox, QComboBox, QRadioButton, QButtonGroup,
    QFrame, QFileDialog, QScrollArea, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from .widgets import DropZone, StatCard
from ..core.models import PriceItem
from ..core.data_manager import ExcelImporter
from ..core.price_engine import PriceValidator, ConflictResolver


class ConflictResolveDialog(QDialog):
    resolved = Signal(PriceItem)

    def __init__(self, item_name: str, items: List[PriceItem], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"同名项目价格冲突 - {item_name}")
        self.setMinimumSize(700, 500)
        self.items = items
        self.selected_index = 0

        layout = QVBoxLayout(self)

        info = QLabel(f"检测到项目 <b style='color:#dc2626'>{item_name}</b> 存在 {len(items)} 条不同价格记录，请选择保留方式：")
        info.setWordWrap(True)
        info.setStyleSheet("padding: 10px; background-color: #fef2f2; border-radius: 6px;")
        layout.addWidget(info)

        self.table = QTableWidget()
        headers = ["选择", "项目名称", "分类", "原价", "会员价", "医生费", "耗材费", "备注"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(items))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)

        self.button_group = QButtonGroup(self)
        for row, item in enumerate(items):
            radio = QRadioButton()
            if row == 0:
                radio.setChecked(True)
            self.button_group.addButton(radio, row)
            self.table.setCellWidget(row, 0, radio)

            values = [
                item.name, item.category,
                f"¥{item.original_price:,.2f}", f"¥{item.member_price:,.2f}",
                f"¥{item.doctor_fee:,.2f}", f"¥{item.material_fee:,.2f}",
                item.remark or "-"
            ]
            for col, val in enumerate(values, 1):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignCenter)
                if row % 2 == 1:
                    cell.setBackground(QBrush(QColor("#fff7ed")))
                self.table.setItem(row, col, cell)

        layout.addWidget(self.table, 1)

        strategy_frame = QFrame()
        strategy_frame.setObjectName("Card")
        s_layout = QVBoxLayout(strategy_frame)
        s_layout.addWidget(QLabel("<b>快捷策略：</b>"))

        btn_row = QHBoxLayout()
        self.btn_highest = QPushButton("保留最高价")
        self.btn_highest.setToolTip("保留原价和会员价均最高的记录")
        self.btn_lowest = QPushButton("保留最低价")
        self.btn_lowest.setToolTip("保留原价和会员价均最低的记录")
        self.btn_latest = QPushButton("保留最新")
        self.btn_latest.setToolTip("保留最后修改的记录")
        self.btn_merge = QPushButton("合并信息")
        self.btn_merge.setToolTip("以选中记录为主，合并其他记录的备注、品牌等信息")
        btn_row.addWidget(self.btn_highest)
        btn_row.addWidget(self.btn_lowest)
        btn_row.addWidget(self.btn_latest)
        btn_row.addWidget(self.btn_merge)
        btn_row.addStretch()
        s_layout.addLayout(btn_row)

        layout.addWidget(strategy_frame)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("确定保留")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.btn_highest.clicked.connect(self._select_highest)
        self.btn_lowest.clicked.connect(self._select_lowest)
        self.btn_latest.clicked.connect(self._select_latest)
        self.btn_merge.clicked.connect(self._select_merge)
        self.button_group.buttonClicked.connect(
            lambda btn: self._set_selected(self.button_group.id(btn))
        )

    def _set_selected(self, idx: int):
        self.selected_index = idx

    def _select_highest(self):
        kept = ConflictResolver.resolve_keep_highest_price(self.items)
        self.selected_index = self.items.index(kept)
        self.button_group.button(self.selected_index).setChecked(True)

    def _select_lowest(self):
        kept = ConflictResolver.resolve_keep_lowest_price(self.items)
        self.selected_index = self.items.index(kept)
        self.button_group.button(self.selected_index).setChecked(True)

    def _select_latest(self):
        kept = ConflictResolver.resolve_keep_latest(self.items)
        self.selected_index = self.items.index(kept)
        self.button_group.button(self.selected_index).setChecked(True)

    def _select_merge(self):
        base = self.items[self.selected_index]
        others = [it for it in self.items if it.id != base.id]
        ConflictResolver.merge_items(base, others)

    def _on_accept(self):
        selected = self.items[self.selected_index]
        others = [it for it in self.items if it.id != selected.id]
        merged = ConflictResolver.merge_items(selected, others)
        self.resolved.emit(merged)
        self.accept()


class ImportPage(QWidget):
    itemsImported = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_items: List[PriceItem] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("导入价目表")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("拖拽 Excel 文件或点击选择，系统将自动识别列字段并处理同名项目冲突")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        stats_row = QHBoxLayout()
        self.stat_total = StatCard("项目总数", "0", "#3b82f6")
        self.stat_categories = StatCard("分类数", "0", "#10b981")
        self.stat_conflicts = StatCard("价格冲突", "0", "#f59e0b")
        self.stat_errors = StatCard("校验问题", "0", "#ef4444")
        stats_row.addWidget(self.stat_total)
        stats_row.addWidget(self.stat_categories)
        stats_row.addWidget(self.stat_conflicts)
        stats_row.addWidget(self.stat_errors)
        layout.addLayout(stats_row)

        self.drop_zone = DropZone()
        self.drop_zone.fileDropped.connect(self._on_file_import)
        layout.addWidget(self.drop_zone)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("Card")
        self.preview_card.setVisible(False)
        preview_layout = QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        preview_layout.setSpacing(12)

        header_row = QHBoxLayout()
        preview_title = QLabel("<b>导入预览</b>")
        header_row.addWidget(preview_title)
        header_row.addStretch()

        self.btn_resolve = QPushButton("⚡ 批量解决冲突")
        self.btn_resolve.setToolTip("自动解决所有冲突：保留最高价")
        self.btn_manual = QPushButton("🔍 逐条处理冲突")
        self.btn_manual.setToolTip("逐个处理冲突项目")
        self.btn_confirm = QPushButton("✓ 确认导入")
        self.btn_confirm.setObjectName("PrimaryButton")
        header_row.addWidget(self.btn_resolve)
        header_row.addWidget(self.btn_manual)
        header_row.addWidget(self.btn_confirm)
        preview_layout.addLayout(header_row)

        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        preview_layout.addWidget(self.preview_table, 1)

        layout.addWidget(self.preview_card, 1)

        self.btn_resolve.clicked.connect(self._auto_resolve)
        self.btn_manual.clicked.connect(self._manual_resolve)
        self.btn_confirm.clicked.connect(self._confirm_import)

    def _on_file_import(self, file_path: str):
        items, warnings = ExcelImporter.import_file(file_path)
        if not items:
            QMessageBox.critical(self, "导入失败", "\n".join(warnings) if warnings else "未识别到有效数据")
            return

        self.current_items = items

        if warnings:
            QMessageBox.warning(self, "导入提示", "\n".join(warnings))

        validations = PriceValidator.run_all_validations(items)
        conflicts = validations["price_conflicts"]
        errors = validations["all_errors"]

        for item in items:
            if item.is_conflict:
                item.is_conflict = True

        categories = set(it.category for it in items)

        self.stat_total.update_value(str(len(items)))
        self.stat_categories.update_value(str(len(categories)))
        self.stat_conflicts.update_value(str(len(conflicts)))
        self.stat_errors.update_value(str(len(errors)))

        self._refresh_preview_table()
        self.preview_card.setVisible(True)

        self.drop_zone.text_label.setText(f"已导入: {file_path.split('/')[-1]}")

    def _refresh_preview_table(self):
        headers = ["状态", "项目名称", "前台展示名", "分类", "原价", "会员价",
                   "医生费", "耗材费", "成本价", "备注"]
        self.preview_table.setColumnCount(len(headers))
        self.preview_table.setHorizontalHeaderLabels(headers)
        self.preview_table.setRowCount(len(self.current_items))

        for row, item in enumerate(self.current_items):
            status_text = "⚠️冲突" if item.is_conflict else "✓正常"
            status_color = "#dc2626" if item.is_conflict else "#059669"
            errors = item.validate()
            if not item.is_conflict and errors:
                status_text = "❗错误"
                status_color = "#f59e0b"

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QBrush(QColor(status_color)))
            status_item.setFont(QFont("", 9, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.preview_table.setItem(row, 0, status_item)

            values = [
                item.name, item.display_name or "-", item.category,
                f"¥{item.original_price:,.2f}" if item.original_price > 0 else "-",
                f"¥{item.member_price:,.2f}" if item.member_price > 0 else "-",
                f"¥{item.doctor_fee:,.2f}" if item.doctor_fee > 0 else "-",
                f"¥{item.material_fee:,.2f}" if item.material_fee > 0 else "-",
                f"¥{item.total_cost:,.2f}" if item.total_cost > 0 else "-",
                item.remark or "-"
            ]
            for col, val in enumerate(values, 1):
                cell = QTableWidgetItem(val)
                if col >= 4:
                    cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                if item.is_conflict:
                    cell.setBackground(QBrush(QColor("#FFF2CC")))
                self.preview_table.setItem(row, col, cell)

        for col in range(len(headers)):
            self.preview_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def _auto_resolve(self):
        duplicates = PriceValidator.check_duplicate_names(self.current_items)
        conflicts = PriceValidator.check_price_conflicts_in_duplicates(duplicates)

        if not conflicts:
            QMessageBox.information(self, "提示", "没有检测到价格冲突")
            return

        resolved_items = {}
        for name, group in conflicts.items():
            kept = ConflictResolver.resolve_keep_highest_price(group)
            others = [it for it in group if it.id != kept.id]
            ConflictResolver.merge_items(kept, others)
            resolved_items[name] = kept

        new_items = []
        seen_names = set()
        for item in self.current_items:
            if item.name in resolved_items:
                if item.name not in seen_names:
                    new_items.append(resolved_items[item.name])
                    seen_names.add(item.name)
            else:
                new_items.append(item)

        self.current_items = new_items
        for it in self.current_items:
            it.is_conflict = False
            it.conflict_ids = []
        self._refresh_preview_table()
        self.stat_conflicts.update_value("0")
        QMessageBox.information(self, "完成", f"已自动解决 {len(resolved_items)} 个冲突（保留最高价策略）")

    def _manual_resolve(self):
        duplicates = PriceValidator.check_duplicate_names(self.current_items)
        conflicts = PriceValidator.check_price_conflicts_in_duplicates(duplicates)

        if not conflicts:
            QMessageBox.information(self, "提示", "没有检测到价格冲突")
            return

        resolved_map = {}
        for name, group in list(conflicts.items()):
            if any(it.id in resolved_map for it in group):
                continue
            dialog = ConflictResolveDialog(name, group, self)
            if dialog.exec() == QDialog.Accepted:
                for it in group:
                    resolved_map[it.id] = False
                kept_idx = dialog.selected_index if hasattr(dialog, 'selected_index') else 0
                kept = group[kept_idx]
                others = [it for it in group if it.id != kept.id]
                ConflictResolver.merge_items(kept, others)
                resolved_map[kept.id] = True
            else:
                return

        new_items = []
        for item in self.current_items:
            if item.id in resolved_map:
                if resolved_map[item.id]:
                    item.is_conflict = False
                    item.conflict_ids = []
                    new_items.append(item)
            else:
                new_items.append(item)

        self.current_items = new_items
        self._refresh_preview_table()

        remaining = sum(1 for it in self.current_items if it.is_conflict)
        self.stat_conflicts.update_value(str(remaining))
        if remaining == 0:
            QMessageBox.information(self, "完成", "所有冲突已处理完毕")

    def _confirm_import(self):
        if not self.current_items:
            QMessageBox.warning(self, "提示", "没有可导入的数据")
            return

        remaining_conflicts = [it for it in self.current_items if it.is_conflict]
        if remaining_conflicts:
            reply = QMessageBox.question(
                self, "确认导入",
                f"还有 {len(remaining_conflicts)} 个冲突项目未解决，导入后可能影响数据准确性。\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        can_save, errors = PriceValidator.can_save(self.current_items)
        if errors:
            reply = QMessageBox.question(
                self, "存在校验问题",
                f"发现 {len(errors)} 个校验问题，部分项目保存时将被拦截：\n\n"
                + "\n".join(errors[:10]) + ("\n..." if len(errors) > 10 else "") +
                f"\n\n是否确认导入？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.itemsImported.emit(self.current_items)
        QMessageBox.information(self, "导入成功", f"已导入 {len(self.current_items)} 个项目，前往其他页面进行编辑吧！")
