from typing import List, Dict
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QFrame, QComboBox, QLineEdit, QSplitter, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont, QAction

from .widgets import StatCard
from ..core.models import PriceItem, CategoryManager
from ..core.price_engine import PriceValidator


class ValidationPage(QWidget):
    itemsUpdated = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_items: List[PriceItem] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("价格校验")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("检查会员价合理性、成本价限制，快速定位和修复价格问题")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        stats_row = QHBoxLayout()
        self.stat_member = StatCard("会员价异常", "0", "#ef4444")
        self.stat_cost = StatCard("低于成本价", "0", "#f59e0b")
        self.stat_dup = StatCard("重名项目", "0", "#8b5cf6")
        self.stat_ok = StatCard("正常项目", "0", "#10b981")
        stats_row.addWidget(self.stat_member)
        stats_row.addWidget(self.stat_cost)
        stats_row.addWidget(self.stat_dup)
        stats_row.addWidget(self.stat_ok)
        layout.addLayout(stats_row)

        filter_card = QFrame()
        filter_card.setObjectName("Card")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(15, 12, 15, 12)

        filter_layout.addWidget(QLabel("筛选："))

        self.filter_issue = QComboBox()
        self.filter_issue.addItem("全部项目", "all")
        self.filter_issue.addItem("会员价高于原价", "member")
        self.filter_issue.addItem("低于成本价", "cost")
        self.filter_issue.addItem("重名项目", "duplicate")
        self.filter_issue.addItem("仅显示有问题", "error")
        filter_layout.addWidget(self.filter_issue)

        self.filter_category = QComboBox()
        self.filter_category.addItem("全部分类", "all")
        for cat in CategoryManager.get_all_categories():
            self.filter_category.addItem(cat, cat)
        filter_layout.addWidget(self.filter_category)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索项目名称...")
        filter_layout.addWidget(self.search_edit, 1)

        self.btn_validate = QPushButton("🔄 重新校验")
        self.btn_validate.setObjectName("PrimaryButton")
        filter_layout.addWidget(self.btn_validate)

        self.btn_fix_member = QPushButton("一键修复会员价")
        self.btn_fix_member.setToolTip("将会员价自动调整为原价的90%")
        self.btn_fix_cost = QPushButton("一键修复成本价")
        self.btn_fix_cost.setToolTip("将低于成本价的项目调整为成本价+10%")
        filter_layout.addWidget(self.btn_fix_member)
        filter_layout.addWidget(self.btn_fix_cost)

        layout.addWidget(filter_card)

        splitter = QSplitter(Qt.Horizontal)

        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        table_title = QLabel("<b>项目列表</b>")
        left_layout.addWidget(table_title)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemChanged.connect(self._on_table_item_changed)
        left_layout.addWidget(self.table, 1)

        splitter.addWidget(left_frame)

        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        detail_title = QLabel("<b>问题详情</b>")
        right_layout.addWidget(detail_title)

        self.issue_list = QTextEdit()
        self.issue_list.setReadOnly(True)
        self.issue_list.setStyleSheet("font-size: 10pt;")
        right_layout.addWidget(self.issue_list, 1)

        action_row = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存修改")
        self.btn_save.setObjectName("SuccessButton")
        self.btn_rollback = QPushButton("↩ 撤销修改")
        action_row.addStretch()
        action_row.addWidget(self.btn_rollback)
        action_row.addWidget(self.btn_save)
        right_layout.addLayout(action_row)

        splitter.addWidget(right_frame)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 300])

        layout.addWidget(splitter, 1)

        self.filter_issue.currentIndexChanged.connect(self._refresh_table)
        self.filter_category.currentIndexChanged.connect(self._refresh_table)
        self.search_edit.textChanged.connect(self._refresh_table)
        self.btn_validate.clicked.connect(self.run_validation)
        self.btn_fix_member.clicked.connect(self._fix_member_prices)
        self.btn_fix_cost.clicked.connect(self._fix_cost_prices)
        self.btn_save.clicked.connect(self._save_changes)
        self.btn_rollback.clicked.connect(self._rollback_changes)
        self.table.itemSelectionChanged.connect(self._show_issues)

        self._original_snapshot = []

    def set_items(self, items: List[PriceItem]):
        self.current_items = items
        self._original_snapshot = [PriceItem(**{k: getattr(it, k) for k in PriceItem.__dataclass_fields__}) for it in items]
        self.run_validation()

    def run_validation(self):
        self.table.blockSignals(True)
        validations = PriceValidator.run_all_validations(self.current_items)
        self.validations = validations

        member_issues = validations["member_above_original"]
        cost_issues = validations["below_cost"]
        duplicates = validations["duplicate_names"]

        self.stat_member.update_value(str(len(member_issues)))
        self.stat_cost.update_value(str(len(cost_issues)))
        self.stat_dup.update_value(str(len(duplicates)))

        ok_count = len(self.current_items) - len(set(
            [x[0].id for x in member_issues] +
            [x[0].id for x in cost_issues] +
            [x.id for grp in duplicates.values() for x in grp]
        ))
        self.stat_ok.update_value(str(max(0, ok_count)))

        self._refresh_table()
        self.table.blockSignals(False)

    def _get_issue_types_for_item(self, item: PriceItem) -> List[str]:
        issues = []
        for it, msg in self.validations.get("member_above_original", []):
            if it.id == item.id:
                issues.append(f"会员价问题: {msg}")
        for it, msg in self.validations.get("below_cost", []):
            if it.id == item.id:
                issues.append(f"成本价问题: {msg}")
        if item.is_conflict:
            issues.append("价格冲突: 同名项目存在不同价格")
        if not issues:
            errors = item.validate()
            issues.extend([f"校验错误: {e}" for e in errors])
        return issues

    def _refresh_table(self):
        self.table.blockSignals(True)
        headers = ["状态", "项目名称", "分类", "原价", "会员价",
                   "医生费", "耗材费", "成本", "总利(会员)", "前台名", "核算名"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        issue_filter = self.filter_issue.currentData()
        cat_filter = self.filter_category.currentData()
        search_text = self.search_edit.text().lower()

        member_ids = {it[0].id for it in self.validations.get("member_above_original", [])}
        cost_ids = {it[0].id for it in self.validations.get("below_cost", [])}
        dup_ids = {it.id for grp in self.validations.get("duplicate_names", {}).values() for it in grp}

        filtered = []
        for item in self.current_items:
            if cat_filter != "all" and item.category != cat_filter:
                continue
            if search_text and search_text not in item.name.lower():
                continue
            issues = self._get_issue_types_for_item(item)
            has_error = len(issues) > 0

            if issue_filter == "all":
                pass
            elif issue_filter == "member" and item.id not in member_ids:
                continue
            elif issue_filter == "cost" and item.id not in cost_ids:
                continue
            elif issue_filter == "duplicate" and item.id not in dup_ids:
                continue
            elif issue_filter == "error" and not has_error:
                continue

            filtered.append((item, issues, member_ids, cost_ids, dup_ids))

        self.table.setRowCount(len(filtered))

        for row, (item, issues, mids, cids, dids) in enumerate(filtered):
            if len(issues) > 1:
                status_text = f"🚨 {len(issues)}项"
                status_color = "#dc2626"
            elif issues:
                status_text = "⚠️ 异常"
                status_color = "#f59e0b"
            else:
                status_text = "✓ 正常"
                status_color = "#059669"

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QBrush(QColor(status_color)))
            status_item.setFont(QFont("", 9, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setData(Qt.UserRole, item.id)
            self.table.setItem(row, 0, status_item)

            editable_fields = [
                (1, "name", None),
                (2, "category", CategoryManager.get_all_categories()),
                (3, "original_price", None),
                (4, "member_price", None),
                (5, "doctor_fee", None),
                (6, "material_fee", None),
                (7, "cost_price", None),
                (8, None, None),
                (9, "display_name", None),
                (10, "internal_name", None),
            ]

            for col, field_name, options in editable_fields:
                if field_name is None:
                    profit = item.member_profit if item.member_price > 0 else item.original_profit
                    profit_color = "#10b981" if profit >= 0 else "#ef4444"
                    profit_item = QTableWidgetItem(f"¥{profit:,.2f}")
                    profit_item.setForeground(QBrush(QColor(profit_color)))
                    profit_item.setTextAlignment(Qt.AlignCenter)
                    profit_item.setFlags(profit_item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(row, col, profit_item)
                    continue

                value = getattr(item, field_name)
                if field_name in ["original_price", "member_price", "doctor_fee", "material_fee", "cost_price"]:
                    text = f"{value:.2f}"
                else:
                    text = str(value or "")

                cell = QTableWidgetItem(text)
                if col >= 3 and col <= 7:
                    cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)

                if item.id in mids and col == 4:
                    cell.setBackground(QBrush(QColor("#fee2e2")))
                if item.id in cids and (col == 3 or col == 4):
                    cell.setBackground(QBrush(QColor("#fef3c7")))
                if item.id in dids:
                    if col not in [3, 4] or (cell.background().style() != Qt.SolidPattern):
                        cell.setBackground(QBrush(QColor("#e9d5ff")))
                if item.id in cids and col == 4:
                    cell.setBackground(QBrush(QColor("#fecaca")))

                self.table.setItem(row, col, cell)

        for col in range(len(headers)):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.blockSignals(False)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        row = item.row()
        col = item.column()
        status_item = self.table.item(row, 0)
        if not status_item:
            return
        item_id = status_item.data(Qt.UserRole)
        target = next((it for it in self.current_items if it.id == item_id), None)
        if not target:
            return

        col_map = {
            1: "name", 2: "category", 3: "original_price", 4: "member_price",
            5: "doctor_fee", 6: "material_fee", 7: "cost_price",
            9: "display_name", 10: "internal_name"
        }
        if col not in col_map:
            return

        field = col_map[col]
        text = item.text().strip()

        try:
            if field in ["original_price", "member_price", "doctor_fee", "material_fee", "cost_price"]:
                value = float(text) if text else 0.0
                setattr(target, field, round(value, 2))
            else:
                setattr(target, field, text)
            target.update_timestamp()
        except ValueError:
            QMessageBox.warning(self, "输入错误", f"请为{field}输入有效的数值")
            return

        self.run_validation()

    def _show_issues(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.issue_list.clear()
            return

        all_issues = []
        for idx in rows:
            status_item = self.table.item(idx.row(), 0)
            if not status_item:
                continue
            item_id = status_item.data(Qt.UserRole)
            item = next((it for it in self.current_items if it.id == item_id), None)
            if item:
                issues = self._get_issue_types_for_item(item)
                if issues:
                    all_issues.append(f"📋 <b>{item.name}</b>")
                    for iss in issues:
                        all_issues.append(f"&nbsp;&nbsp;• {iss}")
                    all_issues.append("")

        self.issue_list.setHtml(
            "<div style='line-height: 1.8;'>" +
            ("<br>".join(all_issues) if all_issues else "<span style='color:#10b981'>✓ 选中项目无问题</span>") +
            "</div>"
        )

    def _fix_member_prices(self):
        count = 0
        for item, _ in self.validations.get("member_above_original", []):
            if item.original_price > 0:
                item.member_price = round(item.original_price * 0.9, 2)
                item.update_timestamp()
                count += 1

        if count > 0:
            self.run_validation()
            QMessageBox.information(self, "修复完成", f"已修复 {count} 个会员价异常（自动调整为原价的90%）")
        else:
            QMessageBox.information(self, "提示", "没有需要修复的会员价")

    def _fix_cost_prices(self):
        count = 0
        for item, _ in self.validations.get("below_cost", []):
            total_cost = item.total_cost
            min_price = round(total_cost * 1.1, 2)
            if item.original_price < min_price:
                item.original_price = min_price
                item.update_timestamp()
            if item.member_price > 0 and item.member_price < min_price:
                item.member_price = round(min_price * 0.95, 2)
                item.update_timestamp()
            count += 1

        if count > 0:
            self.run_validation()
            QMessageBox.information(self, "修复完成", f"已修复 {count} 个低于成本价的项目")
        else:
            QMessageBox.information(self, "提示", "没有需要修复的成本价问题")

    def _save_changes(self):
        can_save, errors = PriceValidator.can_save(self.current_items)
        if not can_save:
            reply = QMessageBox.question(
                self, "存在错误",
                f"发现 {len(errors)} 个问题项目，这些项目保存时可能影响后续计算：\n\n"
                + "\n".join(errors[:8]) + ("\n..." if len(errors) > 8 else "") +
                f"\n\n是否继续保存（有问题的项目将保留）？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self._original_snapshot = [PriceItem(**{k: getattr(it, k) for k in PriceItem.__dataclass_fields__}) for it in self.current_items]
        self.itemsUpdated.emit(self.current_items)
        QMessageBox.information(self, "保存成功", f"已保存 {len(self.current_items)} 个项目的修改")

    def _rollback_changes(self):
        if not self._original_snapshot:
            return
        reply = QMessageBox.question(
            self, "确认撤销",
            f"将撤销所有未保存的修改，恢复到 {len(self._original_snapshot)} 个项目上次保存时的状态。是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.current_items = [PriceItem(**{k: getattr(it, k) for k in PriceItem.__dataclass_fields__}) for it in self._original_snapshot]
        self.run_validation()
        QMessageBox.information(self, "已撤销", "已恢复到上次保存状态")
