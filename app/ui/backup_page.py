import os
from typing import List, Dict, Any
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QFrame, QLineEdit, QTextEdit, QSplitter, QFileDialog, QInputDialog,
    QListWidget, QListWidgetItem, QMenu, QProgressBar, QDialog, QDialogButtonBox,
    QComboBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont, QAction

from .widgets import StatCard
from ..core.models import PriceItem, Snapshot
from ..core.data_manager import BackupManager, OperationLogManager


COMPARE_PRICE_FIELDS = [
    ("original_price", "原价"),
    ("member_price", "会员价"),
    ("doctor_fee", "医生费"),
    ("material_fee", "耗材费"),
    ("cost_price", "成本价"),
]

COMPARE_INFO_FIELDS = [
    ("category", "分类"),
    ("display_name", "前台展示名"),
    ("internal_name", "内部核算名"),
    ("remark", "备注"),
    ("material_brand", "耗材品牌"),
]


def compare_two_snapshots(old_items: List[PriceItem],
                          new_items: List[PriceItem]) -> List[Dict[str, Any]]:
    """对比两个快照（以项目名称为 key），返回差异列表。
    每个元素:
      {"type": "added",   "item": new_item}
      {"type": "removed", "item": old_item}
      {"type": "modified","old_item": old, "new_item": new,
        "price_changes": [(label, ov, nv), ...],
        "info_changes": [(label, ov, nv), ...]}
    """
    old_by_name = {it.name: it for it in old_items if it.name}
    new_by_name = {it.name: it for it in new_items if it.name}
    diffs: List[Dict[str, Any]] = []

    for name, new_it in new_by_name.items():
        if name not in old_by_name:
            diffs.append({"type": "added", "item": new_it})
            continue
        old_it = old_by_name[name]
        price_changes: List = []
        for field, label in COMPARE_PRICE_FIELDS:
            ov = float(getattr(old_it, field, 0.0) or 0.0)
            nv = float(getattr(new_it, field, 0.0) or 0.0)
            if abs(ov - nv) > 0.005:
                price_changes.append((label, ov, nv))
        info_changes: List = []
        for field, label in COMPARE_INFO_FIELDS:
            ov = str(getattr(old_it, field, "") or "")
            nv = str(getattr(new_it, field, "") or "")
            if ov != nv:
                info_changes.append((label, ov, nv))
        if price_changes or info_changes:
            diffs.append({
                "type": "modified",
                "old_item": old_it,
                "new_item": new_it,
                "price_changes": price_changes,
                "info_changes": info_changes,
            })

    for name, old_it in old_by_name.items():
        if name not in new_by_name:
            diffs.append({"type": "removed", "item": old_it})

    return diffs


class SnapshotCompareDialog(QDialog):
    """快照版本对比对话框：选两个快照，查看差异，并支持部分回滚。"""

    partialRollbackRequested = Signal(list)

    def __init__(self, snapshots_meta: List[Dict[str, Any]],
                 backup_manager: BackupManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快照版本对比 · 差异与部分回滚")
        self.setMinimumSize(980, 640)
        self.backup_manager = backup_manager
        self._snapshots_meta = snapshots_meta
        self._snap_cache: Dict[str, List[PriceItem]] = {}
        self._current_diffs: List[Dict[str, Any]] = []

        layout = QVBoxLayout(self)

        tip = QLabel(
            "选择<b>旧版本</b>和<b>新版本</b>两个快照进行对比。勾选要回滚的变更行后点击「回滚选中项」，"
            "即可把选中的几条恢复到<b>旧版本</b>中的状态（新增→删除 / 删除→恢复 / 变更→还原旧值）。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "padding: 10px 14px; background: #eff6ff; color: #1e3a8a;"
            " border-radius: 6px;"
        )
        layout.addWidget(tip)

        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("旧版本（回滚到此状态）："))
        self.cmb_old = QComboBox()
        pick_row.addWidget(self.cmb_old, 1)
        pick_row.addSpacing(16)
        pick_row.addWidget(QLabel("新版本（对比基准）："))
        self.cmb_new = QComboBox()
        pick_row.addWidget(self.cmb_new, 1)
        self.btn_do_compare = QPushButton("🔍 对比差异")
        self.btn_do_compare.setObjectName("PrimaryButton")
        pick_row.addWidget(self.btn_do_compare)
        layout.addLayout(pick_row)

        for meta in snapshots_meta:
            name = meta.get("name", "未命名快照")
            created = (meta.get("created_at", "") or "")[:16]
            cnt = meta.get("item_count", 0)
            label = f"📌 {name}   ({created})   {cnt}项"
            self.cmb_old.addItem(label, meta.get("id"))
            self.cmb_new.addItem(label, meta.get("id"))
        if len(snapshots_meta) >= 2:
            self.cmb_new.setCurrentIndex(0)
            self.cmb_old.setCurrentIndex(min(1, len(snapshots_meta) - 1))

        stats_row = QHBoxLayout()
        self.stat_added = StatCard("新增项目", "0", "#10b981")
        self.stat_removed = StatCard("删除项目", "0", "#ef4444")
        self.stat_modified = StatCard("价格/信息变更", "0", "#f59e0b")
        stats_row.addWidget(self.stat_added)
        stats_row.addWidget(self.stat_removed)
        stats_row.addWidget(self.stat_modified)
        layout.addLayout(stats_row)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_none = QPushButton("取消全选")
        self.btn_rollback_selected = QPushButton("↩️ 回滚选中项")
        self.btn_rollback_selected.setObjectName("PrimaryButton")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_select_none)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_rollback_selected)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.btn_do_compare.clicked.connect(self._do_compare)
        self.btn_select_all.clicked.connect(lambda: self._set_all_checks(True))
        self.btn_select_none.clicked.connect(lambda: self._set_all_checks(False))
        self.btn_rollback_selected.clicked.connect(self._rollback_selected)

        if len(snapshots_meta) >= 2:
            self._do_compare()

    def _load_snapshot_items(self, snap_id: str) -> List[PriceItem]:
        if snap_id not in self._snap_cache:
            self._snap_cache[snap_id] = self.backup_manager.load_snapshot(snap_id) or []
        return self._snap_cache[snap_id]

    def _do_compare(self):
        old_id = self.cmb_old.currentData()
        new_id = self.cmb_new.currentData()
        if not old_id or not new_id or old_id == new_id:
            QMessageBox.warning(self, "提示", "请选择两个不同的快照进行对比")
            return
        old_items = self._load_snapshot_items(old_id)
        new_items = self._load_snapshot_items(new_id)
        if not old_items and not new_items:
            QMessageBox.warning(self, "提示", "所选快照无法加载数据")
            return

        self._current_diffs = compare_two_snapshots(old_items, new_items)
        self._fill_table(self._current_diffs)
        self.stat_added.update_value(str(sum(1 for d in self._current_diffs if d["type"] == "added")))
        self.stat_removed.update_value(str(sum(1 for d in self._current_diffs if d["type"] == "removed")))
        self.stat_modified.update_value(str(sum(1 for d in self._current_diffs if d["type"] == "modified")))

    def _pick_item(self, d: Dict[str, Any]) -> PriceItem:
        if d["type"] == "modified":
            return d["new_item"]
        return d["item"]

    def _fill_table(self, diffs: List[Dict[str, Any]]):
        headers = ["选择", "变更类型", "项目名称", "分类",
                   "旧版本 原价/会员价", "新版本 原价/会员价", "变更详情"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(diffs))

        for row, d in enumerate(diffs):
            chk = QCheckBox()
            self.table.setCellWidget(row, 0, chk)

            t = d["type"]
            if t == "added":
                type_text = "🟢 新增（回滚=删除）"
                item = d["item"]
                category = item.category or "—"
                old_val = "—"
                new_val = (f"¥{item.original_price:,.2f} / "
                           f"¥{item.member_price:,.2f}")
                detail = "新版本中新增的项目"
            elif t == "removed":
                type_text = "🔴 删除（回滚=恢复）"
                item = d["item"]
                category = item.category or "—"
                old_val = (f"¥{item.original_price:,.2f} / "
                           f"¥{item.member_price:,.2f}")
                new_val = "—"
                detail = "新版本中已被删除"
            else:
                type_text = "🟡 变更（回滚=仅还原价格）"
                new_item = d["new_item"]
                old_item = d["old_item"]
                category = new_item.category or "—"
                old_val = (f"¥{old_item.original_price:,.2f} / "
                           f"¥{old_item.member_price:,.2f}")
                new_val = (f"¥{new_item.original_price:,.2f} / "
                           f"¥{new_item.member_price:,.2f}")
                parts = []
                price_changes = d.get("price_changes", [])
                info_changes = d.get("info_changes", [])
                if price_changes:
                    pcs = [f"{lab}: ¥{ov:,.2f}→¥{nv:,.2f}" for lab, ov, nv in price_changes]
                    parts.append("💰价格：" + "；".join(pcs))
                if info_changes:
                    ics = [f"{lab}" for lab, _, _ in info_changes]
                    parts.append("📝信息：" + "、".join(ics) + "（回滚不动此项）")
                detail = " | ".join(parts) if parts else "未记录"

            ref_item = self._pick_item(d)
            name = ref_item.name or "（未命名）"
            for col, text in enumerate([type_text, name, category, old_val, new_val, detail], start=1):
                cell = QTableWidgetItem(str(text))
                if col in (4, 5):
                    cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                if t == "added":
                    cell.setForeground(QBrush(QColor("#047857")))
                elif t == "removed":
                    cell.setForeground(QBrush(QColor("#b91c1c")))
                else:
                    cell.setForeground(QBrush(QColor("#b45309")))
                self.table.setItem(row, col, cell)

        for col in range(len(headers)):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)

    def _set_all_checks(self, checked: bool):
        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, QCheckBox):
                chk.setChecked(checked)

    def _rollback_selected(self):
        if not self._current_diffs:
            QMessageBox.information(self, "提示", "请先对比两个快照")
            return
        selected_diffs: List[Dict[str, Any]] = []
        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if isinstance(chk, QCheckBox) and chk.isChecked():
                selected_diffs.append(self._current_diffs[row])
        if not selected_diffs:
            QMessageBox.information(self, "提示", "请先勾选要回滚的变更行")
            return

        n_added = sum(1 for d in selected_diffs if d["type"] == "added")
        n_removed = sum(1 for d in selected_diffs if d["type"] == "removed")
        n_modified = sum(1 for d in selected_diffs if d["type"] == "modified")

        price_field_labels = [lab for _, lab in COMPARE_PRICE_FIELDS]
        info_field_labels = [lab for _, lab in COMPARE_INFO_FIELDS]

        summary_parts = []
        if n_added:
            summary_parts.append(f"🟢 {n_added} 条新增 → 从当前数据删除")
        if n_removed:
            summary_parts.append(f"🔴 {n_removed} 条删除 → 完整恢复到当前数据")
        if n_modified:
            summary_parts.append(
                f"🟡 {n_modified} 条价格变更 → 仅还原价格字段（"
                + "、".join(price_field_labels) + "）\n"
                + "        ⚠️ 分类、展示名、备注等信息字段保持不变"
            )

        detail_msg = (
            f"将对当前数据应用 {len(selected_diffs)} 条变更：\n\n"
            + "\n".join(f"  {p}" for p in summary_parts)
            + f"\n\n信息类字段（{ '、'.join(info_field_labels) }）不会被回滚覆盖。\n"
            + "是否继续？（回滚前会自动创建当前版本快照）"
        )

        reply = QMessageBox.question(
            self, "确认部分回滚", detail_msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.partialRollbackRequested.emit(selected_diffs)
        self.accept()


class BackupPage(QWidget):
    rollbackRequested = Signal(list)
    partialRollbackRequested = Signal(list)

    def __init__(self, backup_dir: str,
                 log_manager: Optional[OperationLogManager] = None,
                 parent=None):
        super().__init__(parent)
        self.backup_manager = BackupManager(backup_dir)
        self.log_manager = log_manager
        self.current_items: List[PriceItem] = []
        self._init_ui()
        self._refresh_snapshots()
        self._refresh_logs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("备份与恢复")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "保存每次修改的快照，支持整份回滚、两版本对比和部分项目回滚"
        )
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        stats_row = QHBoxLayout()
        self.stat_snapshots = StatCard("总快照数", "0", "#3b82f6")
        self.stat_current = StatCard("当前项目数", "0", "#10b981")
        self.stat_storage = StatCard("备份占用", "0 KB", "#8b5cf6")
        self.stat_latest = StatCard("最近备份", "—", "#f59e0b")
        stats_row.addWidget(self.stat_snapshots)
        stats_row.addWidget(self.stat_current)
        stats_row.addWidget(self.stat_storage)
        stats_row.addWidget(self.stat_latest)
        layout.addLayout(stats_row)

        action_card = QFrame()
        action_card.setObjectName("Card")
        a_layout = QHBoxLayout(action_card)
        a_layout.setContentsMargins(15, 12, 15, 12)

        a_layout.addWidget(QLabel("<b>快速操作：</b>"))

        self.btn_new = QPushButton("📸 立即创建快照")
        self.btn_new.setObjectName("PrimaryButton")
        self.btn_compare = QPushButton("🆚 版本对比")
        self.btn_compare.setToolTip("选择两个快照对比差异，只回滚选中的几条")
        self.btn_export = QPushButton("📦 导出备份文件")
        self.btn_import = QPushButton("📥 导入备份文件")
        self.btn_clean = QPushButton("🗑️ 清理旧备份")

        a_layout.addWidget(self.btn_new)
        a_layout.addWidget(self.btn_compare)
        a_layout.addWidget(self.btn_export)
        a_layout.addWidget(self.btn_import)
        a_layout.addStretch()
        a_layout.addWidget(self.btn_clean)
        layout.addWidget(action_card)

        splitter = QSplitter(Qt.Horizontal)

        left = QFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # --- Tab 切换按钮（快照列表 / 操作记录）
        tab_bar = QFrame()
        tab_bar.setStyleSheet("QFrame { background: #f1f5f9; border-radius: 6px; padding: 2px; }")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(2, 2, 2, 2)
        tab_layout.setSpacing(2)

        self.btn_tab_snapshots = QPushButton("📋 快照列表")
        self.btn_tab_snapshots.setCheckable(True)
        self.btn_tab_snapshots.setChecked(True)
        self.btn_tab_snapshots.setCursor(Qt.PointingHandCursor)
        self.btn_tab_snapshots.setStyleSheet("""
            QPushButton {
                background: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 600;
                color: #1e293b;
            }
            QPushButton:checked {
                background: #3b82f6;
                color: white;
            }
        """)

        self.btn_tab_logs = QPushButton("⏱️ 操作记录")
        self.btn_tab_logs.setCheckable(True)
        self.btn_tab_logs.setCursor(Qt.PointingHandCursor)
        self.btn_tab_logs.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
                color: #64748b;
            }
            QPushButton:checked {
                background: #3b82f6;
                color: white;
            }
        """)

        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_tab_snapshots, 0)
        self.tab_group.addButton(self.btn_tab_logs, 1)
        self.tab_group.setExclusive(True)

        tab_layout.addWidget(self.btn_tab_snapshots)
        tab_layout.addWidget(self.btn_tab_logs)
        tab_layout.addStretch()
        left_layout.addWidget(tab_bar)

        # --- 内容区：快照列表 + 操作记录（QStackedWidget 切换）
        self.list_stack = QStackedWidget()

        # 页面1：快照列表
        snap_page = QWidget()
        snap_layout = QVBoxLayout(snap_page)
        snap_layout.setContentsMargins(0, 0, 0, 0)
        snap_layout.setSpacing(8)

        snap_header = QHBoxLayout()
        snap_header.addWidget(QLabel("<b>📋 快照列表</b>"))
        snap_header.addStretch()
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("刷新列表")
        self.btn_refresh.setFixedWidth(36)
        snap_header.addWidget(self.btn_refresh)
        snap_layout.addLayout(snap_header)

        self.snapshot_list = QListWidget()
        self.snapshot_list.setContextMenuPolicy(Qt.CustomContextMenu)
        snap_layout.addWidget(self.snapshot_list, 1)

        self.list_stack.addWidget(snap_page)

        # 页面2：操作记录
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("<b>⏱️ 操作记录</b>"))
        log_header.addStretch()
        self.btn_log_refresh = QPushButton("🔄")
        self.btn_log_refresh.setToolTip("刷新记录")
        self.btn_log_refresh.setFixedWidth(36)
        log_header.addWidget(self.btn_log_refresh)
        log_layout.addLayout(log_header)

        self.log_list = QListWidget()
        self.log_list.setContextMenuPolicy(Qt.CustomContextMenu)
        log_layout.addWidget(self.log_list, 1)

        log_footer = QLabel("显示最近 100 条操作记录")
        log_footer.setStyleSheet("color: #94a3b8; font-size: 8pt; padding: 4px 8px;")
        log_layout.addWidget(log_footer)

        self.list_stack.addWidget(log_page)

        left_layout.addWidget(self.list_stack, 1)

        splitter.addWidget(left)

        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.right_title = QLabel("<b>📄 快照详情</b>")
        right_layout.addWidget(self.right_title)

        self.detail_stack = QStackedWidget()

        # --- 页1：快照详情
        snap_detail_page = QFrame()
        snap_d_layout = QVBoxLayout(snap_detail_page)
        snap_d_layout.setContentsMargins(0, 0, 0, 0)
        snap_d_layout.setSpacing(0)

        self.detail_card = QFrame()
        self.detail_card.setObjectName("Card")
        d_layout = QVBoxLayout(self.detail_card)
        d_layout.setContentsMargins(15, 12, 15, 12)
        d_layout.setSpacing(10)

        self.detail_name = QLabel("请选择左侧的快照查看详情")
        self.detail_name.setStyleSheet("font-size: 12pt; font-weight: bold; color: #1e293b;")
        d_layout.addWidget(self.detail_name)

        self.detail_time = QLabel("")
        self.detail_time.setStyleSheet("color: #64748b;")
        d_layout.addWidget(self.detail_time)

        self.detail_desc = QLabel("")
        self.detail_desc.setWordWrap(True)
        self.detail_desc.setStyleSheet("color: #475569; padding: 8px 0;")
        d_layout.addWidget(self.detail_desc)

        info_grid = QHBoxLayout()
        self.detail_count = QLabel("项目数：-")
        self.detail_count.setStyleSheet("padding: 8px 12px; background: #eff6ff; border-radius: 6px; color: #1e40af;")
        self.detail_id = QLabel("")
        self.detail_id.setStyleSheet("padding: 8px 12px; background: #f8fafc; border-radius: 6px; color: #64748b; font-size: 9pt;")
        self.detail_id.setWordWrap(True)
        info_grid.addWidget(self.detail_count, 1)
        info_grid.addWidget(self.detail_id, 2)
        d_layout.addLayout(info_grid)

        d_layout.addWidget(QLabel("<b>包含项目预览</b>"))
        self.detail_table = QTableWidget()
        self.detail_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.verticalHeader().setVisible(False)
        d_layout.addWidget(self.detail_table, 1)

        btn_row = QHBoxLayout()
        self.btn_rollback = QPushButton("↩️ 回滚到此版本")
        self.btn_rollback.setObjectName("PrimaryButton")
        self.btn_rollback.setEnabled(False)
        self.btn_delete = QPushButton("🗑️ 删除此快照")
        self.btn_delete.setObjectName("DangerButton")
        self.btn_delete.setEnabled(False)
        self.btn_export_snap = QPushButton("📤 单独导出")
        btn_row.addStretch()
        btn_row.addWidget(self.btn_export_snap)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_rollback)
        d_layout.addLayout(btn_row)

        snap_d_layout.addWidget(self.detail_card)
        self.detail_stack.addWidget(snap_detail_page)

        # --- 页2：操作记录详情
        log_detail_page = QFrame()
        log_d_layout = QVBoxLayout(log_detail_page)
        log_d_layout.setContentsMargins(0, 0, 0, 0)

        self.log_detail_card = QFrame()
        self.log_detail_card.setObjectName("Card")
        ld_layout = QVBoxLayout(self.log_detail_card)
        ld_layout.setContentsMargins(15, 12, 15, 12)
        ld_layout.setSpacing(10)

        self.log_detail_type = QLabel("请选择左侧的操作记录查看详情")
        self.log_detail_type.setStyleSheet("font-size: 12pt; font-weight: bold; color: #1e293b;")
        ld_layout.addWidget(self.log_detail_type)

        self.log_detail_time = QLabel("")
        self.log_detail_time.setStyleSheet("color: #64748b;")
        ld_layout.addWidget(self.log_detail_time)

        self.log_detail_action = QLabel("")
        self.log_detail_action.setWordWrap(True)
        self.log_detail_action.setStyleSheet("color: #334155; padding: 6px 0;")
        ld_layout.addWidget(self.log_detail_action)

        log_info_grid = QHBoxLayout()
        self.log_detail_count = QLabel("项目数：-")
        self.log_detail_count.setStyleSheet("padding: 8px 12px; background: #eff6ff; border-radius: 6px; color: #1e40af;")
        self.log_detail_id = QLabel("")
        self.log_detail_id.setStyleSheet("padding: 8px 12px; background: #f8fafc; border-radius: 6px; color: #64748b; font-size: 9pt;")
        self.log_detail_id.setWordWrap(True)
        log_info_grid.addWidget(self.log_detail_count, 1)
        log_info_grid.addWidget(self.log_detail_id, 2)
        ld_layout.addLayout(log_info_grid)

        ld_layout.addWidget(QLabel("<b>操作详情</b>"))
        self.log_detail_text = QTextEdit()
        self.log_detail_text.setReadOnly(True)
        self.log_detail_text.setStyleSheet("font-size: 10pt;")
        ld_layout.addWidget(self.log_detail_text, 1)

        log_btn_row = QHBoxLayout()
        self.btn_log_jump_snapshot = QPushButton("📌 跳到对应快照")
        self.btn_log_jump_snapshot.setObjectName("PrimaryButton")
        self.btn_log_jump_snapshot.setEnabled(False)
        log_btn_row.addStretch()
        log_btn_row.addWidget(self.btn_log_jump_snapshot)
        ld_layout.addLayout(log_btn_row)

        log_d_layout.addWidget(self.log_detail_card)
        self.detail_stack.addWidget(log_detail_page)

        right_layout.addWidget(self.detail_stack, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([350, 700])

        layout.addWidget(splitter, 1)

        self.btn_new.clicked.connect(self._create_new_snapshot)
        self.btn_compare.clicked.connect(self._open_compare_dialog)
        self.btn_export.clicked.connect(self._export_all)
        self.btn_import.clicked.connect(self._import_backup)
        self.btn_clean.clicked.connect(self._clean_old)
        self.btn_refresh.clicked.connect(self._refresh_snapshots)
        self.btn_log_refresh.clicked.connect(self._refresh_logs)
        self.btn_rollback.clicked.connect(self._do_rollback)
        self.btn_delete.clicked.connect(self._delete_current)
        self.btn_export_snap.clicked.connect(self._export_current)
        self.snapshot_list.currentItemChanged.connect(self._on_select_snapshot)
        self.snapshot_list.customContextMenuRequested.connect(self._show_context_menu)
        self.log_list.currentItemChanged.connect(self._on_select_log)
        self.btn_tab_snapshots.clicked.connect(lambda: self._switch_tab(0))
        self.btn_tab_logs.clicked.connect(lambda: self._switch_tab(1))

    def _open_compare_dialog(self):
        if not self._all_snapshots or len(self._all_snapshots) < 2:
            QMessageBox.information(
                self, "提示",
                "至少需要 2 个快照才能做版本对比。\n请先创建至少两个快照。"
            )
            return
        dlg = SnapshotCompareDialog(self._all_snapshots, self.backup_manager, self)
        dlg.partialRollbackRequested.connect(self._handle_partial_rollback)
        dlg.exec()

    def _handle_partial_rollback(self, diffs: List[Dict[str, Any]]):
        """接收对比对话框的部分回滚请求，把 diff 应用到 current_items。
        规则：
          added    → 从当前数据中删除该项目（匹配 name）
          removed  → 把旧版本项目完整恢复到当前数据
          modified → 仅还原价格字段（原价/会员价/医生费/耗材费/成本价），
                     不动分类、展示名、核算名、备注、品牌等信息字段
        """
        if not self.current_items:
            QMessageBox.warning(self, "提示", "当前没有任何项目数据，无法应用部分回滚")
            return
        current_by_name = {it.name: it for it in self.current_items if it.name}
        applied = 0
        price_fields = [f for f, _ in COMPARE_PRICE_FIELDS]

        for d in diffs:
            t = d["type"]
            if t == "added":
                name = d["item"].name
                if name in current_by_name:
                    self.current_items.remove(current_by_name[name])
                    del current_by_name[name]
                    applied += 1
            elif t == "removed":
                old_it = d["item"]
                if old_it.name not in current_by_name:
                    from dataclasses import replace
                    restored = replace(old_it)
                    self.current_items.append(restored)
                    current_by_name[restored.name] = restored
                    applied += 1
            elif t == "modified":
                old_it = d["old_item"]
                target = current_by_name.get(old_it.name)
                if target is not None:
                    for field in price_fields:
                        if hasattr(target, field) and hasattr(old_it, field):
                            setattr(target, field, getattr(old_it, field))
                    target.update_timestamp()
                    applied += 1

        if applied == 0:
            QMessageBox.information(self, "提示", "选中的变更在当前数据中都不存在，未应用任何修改")
            return

        # 整份回滚前自动快照
        try:
            self.backup_manager.create_snapshot(
                self.current_items,
                name=f"部分回滚前备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                description="部分回滚前自动备份",
            )
        except Exception:
            pass

        self.partialRollbackRequested.emit(list(self.current_items))
        self._refresh_snapshots()
        QMessageBox.information(
            self, "部分回滚完成",
            f"已成功应用 {applied} 条变更到当前数据。\n\n"
            f"（整份数据版本已通过 partialRollbackRequested 信号发出，需要到各页面同步）"
        )

    def set_items(self, items: List[PriceItem]):
        self.current_items = items
        self.stat_current.update_value(str(len(items)))

    def _switch_tab(self, idx: int):
        """切换左侧 Tab（0=快照列表，1=操作记录）"""
        self.list_stack.setCurrentIndex(idx)
        self.detail_stack.setCurrentIndex(idx)
        if idx == 0:
            self.right_title.setText("<b>📄 快照详情</b>")
        else:
            self.right_title.setText("<b>⏱️ 操作记录详情</b>")

    def _refresh_logs(self):
        """刷新操作记录列表。"""
        self.log_list.clear()
        if self.log_manager is None:
            return
        logs = self.log_manager.list_logs(limit=100)
        for log in logs:
            item = QListWidgetItem()
            log_type = log.get("type", "snapshot")
            type_info = OperationLogManager.LOG_TYPES.get(
                log_type, {"label": "📝 操作", "color": "#64748b"}
            )
            label = type_info.get("label", "操作")
            action = log.get("action", "")
            created = log.get("created_at", "")
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created)
                time_str = dt.strftime("%m-%d %H:%M")
            except Exception:
                time_str = created[:16] if created else ""

            cnt = log.get("item_count", 0)
            item.setText(f"{label}\n   {action}\n   🕒 {time_str}  |  📦 {cnt}项")
            item.setData(Qt.UserRole, log.get("id", ""))
            item.setForeground(QBrush(QColor(type_info.get("color", "#334155"))))
            self.log_list.addItem(item)

    def _on_select_log(self, current: QListWidgetItem, previous: QListWidgetItem):
        """选中操作记录时显示详情。"""
        if not current or self.log_manager is None:
            return
        log_id = current.data(Qt.UserRole)
        log = self.log_manager.get_log(log_id)
        if not log:
            return

        log_type = log.get("type", "snapshot")
        type_info = OperationLogManager.LOG_TYPES.get(
            log_type, {"label": "📝 操作", "color": "#64748b"}
        )
        self.log_detail_type.setText(type_info.get("label", "操作"))
        self.log_detail_type.setStyleSheet(
            f"font-size: 12pt; font-weight: bold; color: {type_info.get('color', '#1e293b')};"
        )

        created = log.get("created_at", "")
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(created)
            time_str = dt.strftime("%Y年%m月%d日 %H:%M:%S")
        except Exception:
            time_str = created or ""
        self.log_detail_time.setText(f"🕒 操作时间：{time_str}")

        self.log_detail_action.setText(f"📝 {log.get('action', '')}")

        cnt = log.get("item_count", 0)
        self.log_detail_count.setText(f"📦 项目数：{cnt} 个")

        lid = log.get("id", "")
        self.log_detail_id.setText(f"ID: {lid[:8]}...{lid[-4:]}")

        # 详情内容
        detail = log.get("detail", {})
        lines = []
        if detail:
            for k, v in detail.items():
                k_label = {
                    "source_file": "源文件",
                    "added": "新增项目数",
                    "removed": "删除项目数",
                    "modified": "修改项目数",
                    "adjust_type": "调整方式",
                    "percentage": "调整幅度",
                    "amount": "调整金额",
                    "target_field": "目标字段",
                    "rollback_type": "回滚类型",
                    "snapshot_name": "快照名称",
                    "from_snapshot": "来源快照",
                    "to_snapshot": "目标快照",
                    "reason": "原因",
                }.get(k, k)
                lines.append(f"<b>{k_label}：</b>{v}")
        else:
            lines.append("无详细信息")
        self.log_detail_text.setHtml(
            "<div style='line-height: 2;'>" + "<br>".join(lines) + "</div>"
        )

        # 关联快照
        snap_id = log.get("snapshot_id", "")
        has_snapshot = bool(snap_id)
        self.btn_log_jump_snapshot.setEnabled(has_snapshot)
        self.btn_log_jump_snapshot.setProperty("target_snapshot_id", snap_id)
        if has_snapshot:
            self.btn_log_jump_snapshot.clicked.connect(self._jump_to_snapshot_from_log)
        else:
            try:
                self.btn_log_jump_snapshot.clicked.disconnect()
            except Exception:
                pass

    def _jump_to_snapshot_from_log(self):
        """从操作记录跳到对应快照。"""
        snap_id = self.btn_log_jump_snapshot.property("target_snapshot_id")
        if not snap_id:
            return
        # 切到快照 Tab
        self._switch_tab(0)
        self.btn_tab_snapshots.setChecked(True)
        # 在列表中找到并选中
        for i in range(self.snapshot_list.count()):
            item = self.snapshot_list.item(i)
            if item and item.data(Qt.UserRole) == snap_id:
                self.snapshot_list.setCurrentRow(i)
                break

    def _refresh_snapshots(self):
        snapshots = self.backup_manager.list_snapshots()
        self._all_snapshots = snapshots

        self.snapshot_list.clear()
        for snap in snapshots:
            item = QListWidgetItem()
            created = snap.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = created

            name = snap.get("name", "未命名快照")
            count = snap.get("item_count", 0)
            item.setText(f"📌 {name}\n   📅 {time_str}  |  📦 {count}项")
            item.setData(Qt.UserRole, snap.get("id"))
            self.snapshot_list.addItem(item)

        self.stat_snapshots.update_value(str(len(snapshots)))

        total_size = 0
        backup_dir = self.backup_manager.backup_dir
        if os.path.exists(backup_dir):
            for root, dirs, files in os.walk(backup_dir):
                for f in files:
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass

        if total_size < 1024:
            size_str = f"{total_size} B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        self.stat_storage.update_value(size_str)

        if snapshots:
            latest = snapshots[0].get("created_at", "")
            try:
                dt = datetime.fromisoformat(latest)
                self.stat_latest.update_value(dt.strftime("%m-%d %H:%M"))
            except Exception:
                self.stat_latest.update_value(latest[:16] if latest else "—")
        else:
            self.stat_latest.update_value("—")

        self._clear_detail()

    def _clear_detail(self):
        self.detail_name.setText("请选择左侧的快照查看详情")
        self.detail_time.setText("")
        self.detail_desc.setText("")
        self.detail_count.setText("项目数：-")
        self.detail_id.setText("")
        self.detail_table.setRowCount(0)
        self.detail_table.setColumnCount(0)
        self.btn_rollback.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self._current_selected_id = None

    def _on_select_snapshot(self, current: QListWidgetItem, previous: QListWidgetItem):
        if not current:
            self._clear_detail()
            return

        snap_id = current.data(Qt.UserRole)
        self._current_selected_id = snap_id
        self._load_detail(snap_id)

    def _load_detail(self, snap_id: str):
        items = self.backup_manager.load_snapshot(snap_id)
        snap_meta = next((s for s in self._all_snapshots if s.get("id") == snap_id), None)

        if items is None or snap_meta is None:
            QMessageBox.warning(self, "错误", "无法加载快照数据")
            return

        self.detail_name.setText("📌 " + snap_meta.get("name", "未命名"))

        created = snap_meta.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created)
            time_str = dt.strftime("%Y年%m月%d日 %H:%M:%S")
        except Exception:
            time_str = created
        self.detail_time.setText(f"🕒 创建时间：{time_str}")

        desc = snap_meta.get("description", "")
        self.detail_desc.setText(f"📝 备注：{desc}" if desc else "📝 备注：（无）")

        self.detail_count.setText(f"📦 项目数：{snap_meta.get('item_count', len(items))} 个")
        self.detail_id.setText(f"ID: {snap_id[:8]}...{snap_id[-4:]}")

        headers = ["项目名称", "分类", "原价", "会员价", "成本", "备注"]
        self.detail_table.setColumnCount(len(headers))
        self.detail_table.setHorizontalHeaderLabels(headers)
        self.detail_table.setRowCount(min(len(items), 100))

        for row, it in enumerate(items[:100]):
            values = [
                it.name or "-",
                it.category or "-",
                f"¥{it.original_price:,.2f}" if it.original_price > 0 else "-",
                f"¥{it.member_price:,.2f}" if it.member_price > 0 else "-",
                f"¥{it.total_cost:,.2f}" if it.total_cost > 0 else "-",
                it.remark or "-"
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(val)
                if col >= 2:
                    cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                self.detail_table.setItem(row, col, cell)

        for col in range(len(headers)):
            self.detail_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.detail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        if len(items) > 100:
            self.detail_table.insertRow(100)
            cell = QTableWidgetItem(f"... 仅显示前100条，共 {len(items)} 条记录 ...")
            cell.setTextAlignment(Qt.AlignCenter)
            cell.setForeground(QBrush(QColor("#64748b")))
            self.detail_table.setItem(100, 0, cell)

        self.btn_rollback.setEnabled(True)
        self.btn_delete.setEnabled(True)

    def _create_new_snapshot(self):
        if not self.current_items:
            QMessageBox.warning(self, "提示", "当前没有项目数据，请先导入或创建项目")
            return

        name, ok1 = QInputDialog.getText(
            self, "新建快照", "快照名称：",
            text=f"手动备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        if not ok1:
            return

        desc, ok2 = QInputDialog.getMultiLineText(
            self, "新建快照", "备注说明（可选）：", ""
        )
        if not ok2:
            return

        try:
            snap = self.backup_manager.create_snapshot(
                self.current_items, name=name, description=desc
            )
            self._refresh_snapshots()
            QMessageBox.information(self, "创建成功",
                                    f"快照已保存\n\n名称：{snap.name}\n项目数：{snap.item_count}个")
        except Exception as e:
            QMessageBox.critical(self, "创建失败", f"创建快照失败：{str(e)}")

    def _do_rollback(self):
        if not hasattr(self, "_current_selected_id") or not self._current_selected_id:
            return

        items = self.backup_manager.load_snapshot(self._current_selected_id)
        if items is None:
            QMessageBox.warning(self, "错误", "无法加载该快照的数据")
            return

        snap_meta = next((s for s in self._all_snapshots if s.get("id") == self._current_selected_id), None)
        snap_name = snap_meta.get("name", "该版本") if snap_meta else "该版本"

        diff_info = ""
        if self.current_items:
            diff = len(items) - len(self.current_items)
            if diff > 0:
                diff_info = f"比当前多 {diff} 个项目"
            elif diff < 0:
                diff_info = f"比当前少 {abs(diff)} 个项目"
            else:
                diff_info = "项目数量与当前相同"

        reply = QMessageBox.question(
            self, "确认回滚",
            f"确定要回滚到 <b>{snap_name}</b> 吗？\n\n"
            f"该快照包含 {len(items)} 个项目，{diff_info}。\n\n"
            f"⚠️ 回滚前将自动创建当前版本的备份。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            if self.current_items:
                self.backup_manager.create_snapshot(
                    self.current_items,
                    name=f"回滚前备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    description=f"回滚到 {snap_name} 前的自动备份"
                )

            self.rollbackRequested.emit(items)
            self._refresh_snapshots()
            QMessageBox.information(self, "回滚成功",
                                    f"已回滚到 {snap_name}\n\n"
                                    f"共加载 {len(items)} 个项目，当前版本已自动备份。")
        except Exception as e:
            QMessageBox.critical(self, "回滚失败", f"回滚操作失败：{str(e)}")

    def _delete_current(self):
        if not hasattr(self, "_current_selected_id") or not self._current_selected_id:
            return

        snap_meta = next((s for s in self._all_snapshots if s.get("id") == self._current_selected_id), None)
        snap_name = snap_meta.get("name", "该版本") if snap_meta else "该版本"

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除快照 <b>{snap_name}</b> 吗？\n\n此操作无法撤销！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if self.backup_manager.delete_snapshot(self._current_selected_id):
            self._refresh_snapshots()
            QMessageBox.information(self, "已删除", "快照已被永久删除")

    def _show_context_menu(self, pos):
        item = self.snapshot_list.itemAt(pos)
        if not item:
            return
        self.snapshot_list.setCurrentItem(item)

        menu = QMenu(self)
        act_rollback = QAction("↩️ 回滚到此版本", self)
        act_export = QAction("📤 导出此快照", self)
        act_rename = QAction("✏️ 重命名", self)
        act_delete = QAction("🗑️ 删除", self)

        menu.addAction(act_rollback)
        menu.addAction(act_export)
        menu.addSeparator()
        menu.addAction(act_rename)
        menu.addAction(act_delete)

        action = menu.exec(self.snapshot_list.mapToGlobal(pos))
        if action == act_rollback:
            self._do_rollback()
        elif action == act_export:
            self._export_current()
        elif action == act_rename:
            self._rename_current()
        elif action == act_delete:
            self._delete_current()

    def _rename_current(self):
        if not hasattr(self, "_current_selected_id") or not self._current_selected_id:
            return

        current_meta = next((s for s in self._all_snapshots if s.get("id") == self._current_selected_id), None)
        if not current_meta:
            return

        new_name, ok = QInputDialog.getText(
            self, "重命名快照", "新名称：", text=current_meta.get("name", "")
        )
        if not ok or not new_name.strip():
            return

        for s in self._all_snapshots:
            if s.get("id") == self._current_selected_id:
                s["name"] = new_name.strip()
                break

        self.backup_manager._save_index()
        self._refresh_snapshots()

        for i in range(self.snapshot_list.count()):
            item = self.snapshot_list.item(i)
            if item.data(Qt.UserRole) == self._current_selected_id:
                self.snapshot_list.setCurrentRow(i)
                break

    def _export_current(self):
        if not hasattr(self, "_current_selected_id") or not self._current_selected_id:
            return

        items = self.backup_manager.load_snapshot(self._current_selected_id)
        if items is None:
            QMessageBox.warning(self, "错误", "无法加载快照数据")
            return

        snap_meta = next((s for s in self._all_snapshots if s.get("id") == self._current_selected_id), None)
        default_name = f"{snap_meta.get('name', 'snapshot') if snap_meta else 'snapshot'}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出快照", default_name, "JSON 备份文件 (*.json)"
        )
        if not file_path:
            return

        import json
        try:
            data = {
                "name": snap_meta.get("name") if snap_meta else "",
                "description": snap_meta.get("description") if snap_meta else "",
                "exported_at": datetime.now().isoformat(),
                "items": [it.to_dict() for it in items]
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出成功", f"快照已导出到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败：{str(e)}")

    def _export_all(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出全部备份",
            f"全部备份_{datetime.now().strftime('%Y%m%d')}.json",
            "JSON 备份文件 (*.json)"
        )
        if not file_path:
            return

        import json
        try:
            all_data = {
                "exported_at": datetime.now().isoformat(),
                "snapshot_count": len(self._all_snapshots),
                "snapshots": []
            }
            for snap_meta in self._all_snapshots:
                snap_id = snap_meta.get("id")
                items = self.backup_manager.load_snapshot(snap_id)
                if items is not None:
                    all_data["snapshots"].append({
                        "meta": snap_meta,
                        "items": [it.to_dict() for it in items]
                    })

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出成功",
                                    f"已导出 {len(all_data['snapshots'])} 个快照到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出失败：{str(e)}")

    def _import_backup(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入备份文件", "", "JSON 备份文件 (*.json);;所有文件 (*.*)"
        )
        if not file_path:
            return

        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "items" in data and "name" in data:
                items = []
                for item_data in data.get("items", []):
                    from ..core.models import PriceItem
                    fields = {k: v for k, v in item_data.items()
                              if k in PriceItem.__dataclass_fields__}
                    items.append(PriceItem(**fields))

                reply = QMessageBox.question(
                    self, "导入快照",
                    f"文件包含 1 个快照（{len(items)} 个项目）。\n\n"
                    f"点击「是」立即恢复到此版本，点击「否」仅保存为备份不恢复。",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                if reply == QMessageBox.Cancel:
                    return

                snap = self.backup_manager.create_snapshot(
                    items,
                    name=data.get("name") or f"导入_{datetime.now().strftime('%Y%m%d')}",
                    description=data.get("description", "") or f"从 {os.path.basename(file_path)} 导入"
                )
                self._refresh_snapshots()

                if reply == QMessageBox.Yes:
                    self.rollbackRequested.emit(items)
                QMessageBox.information(self, "导入成功", f"已导入为快照：{snap.name}")

            elif "snapshots" in data:
                snaps = data.get("snapshots", [])
                count = 0
                for entry in snaps:
                    meta = entry.get("meta", {})
                    items_data = entry.get("items", [])
                    items = []
                    for item_data in items_data:
                        from ..core.models import PriceItem
                        fields = {k: v for k, v in item_data.items()
                                  if k in PriceItem.__dataclass_fields__}
                        items.append(PriceItem(**fields))
                    self.backup_manager.create_snapshot(
                        items,
                        name=meta.get("name") or f"导入快照_{count+1}",
                        description=meta.get("description", "") or f"从 {os.path.basename(file_path)} 导入"
                    )
                    count += 1
                self._refresh_snapshots()
                QMessageBox.information(self, "导入成功", f"已导入 {count} 个快照")
            else:
                QMessageBox.warning(self, "格式错误", "文件格式不正确，无法识别")

        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入失败：{str(e)}")

    def _clean_old(self):
        if not self._all_snapshots:
            QMessageBox.information(self, "提示", "当前没有任何快照，无需清理")
            return

        days, ok = QInputDialog.getInt(
            self, "清理旧备份",
            "删除多少天以前的快照？（保留最近7天）",
            value=7, minValue=1, maxValue=365
        )
        if not ok:
            return

        import time
        cutoff = time.time() - days * 86400
        to_delete = []
        for snap in self._all_snapshots:
            try:
                ts = datetime.fromisoformat(snap.get("created_at", "")).timestamp()
                if ts < cutoff:
                    to_delete.append(snap.get("id"))
            except Exception:
                continue

        if not to_delete:
            QMessageBox.information(self, "无需清理", f"没有发现超过 {days} 天的快照")
            return

        reply = QMessageBox.question(
            self, "确认清理",
            f"将删除 {len(to_delete)} 个超过 {days} 天的快照。\n\n此操作无法撤销！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        for sid in to_delete:
            self.backup_manager.delete_snapshot(sid)

        self._refresh_snapshots()
        QMessageBox.information(self, "清理完成", f"已删除 {len(to_delete)} 个旧快照")
