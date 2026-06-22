import os
from typing import List, Dict, Any
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QFrame, QLineEdit, QTextEdit, QSplitter, QFileDialog, QInputDialog,
    QListWidget, QListWidgetItem, QMenu, QProgressBar
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont, QAction

from .widgets import StatCard
from ..core.models import PriceItem, Snapshot
from ..core.data_manager import BackupManager


class BackupPage(QWidget):
    rollbackRequested = Signal(list)

    def __init__(self, backup_dir: str, parent=None):
        super().__init__(parent)
        self.backup_manager = BackupManager(backup_dir)
        self.current_items: List[PriceItem] = []
        self._init_ui()
        self._refresh_snapshots()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("备份与恢复")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("保存每次修改的快照，误操作时一键回滚到任意历史版本")
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
        self.btn_export = QPushButton("📦 导出备份文件")
        self.btn_import = QPushButton("📥 导入备份文件")
        self.btn_clean = QPushButton("🗑️ 清理旧备份")

        a_layout.addWidget(self.btn_new)
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

        left_header = QHBoxLayout()
        left_header.addWidget(QLabel("<b>📋 快照列表</b>"))
        left_header.addStretch()
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("刷新列表")
        self.btn_refresh.setFixedWidth(36)
        left_header.addWidget(self.btn_refresh)
        left_layout.addLayout(left_header)

        self.snapshot_list = QListWidget()
        self.snapshot_list.setContextMenuPolicy(Qt.CustomContextMenu)
        left_layout.addWidget(self.snapshot_list, 1)

        splitter.addWidget(left)

        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        detail_title = QLabel("<b>📄 快照详情</b>")
        right_layout.addWidget(detail_title)

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

        right_layout.addWidget(self.detail_card, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([350, 700])

        layout.addWidget(splitter, 1)

        self.btn_new.clicked.connect(self._create_new_snapshot)
        self.btn_export.clicked.connect(self._export_all)
        self.btn_import.clicked.connect(self._import_backup)
        self.btn_clean.clicked.connect(self._clean_old)
        self.btn_refresh.clicked.connect(self._refresh_snapshots)
        self.btn_rollback.clicked.connect(self._do_rollback)
        self.btn_delete.clicked.connect(self._delete_current)
        self.btn_export_snap.clicked.connect(self._export_current)
        self.snapshot_list.currentItemChanged.connect(self._on_select_snapshot)
        self.snapshot_list.customContextMenuRequested.connect(self._show_context_menu)

    def set_items(self, items: List[PriceItem]):
        self.current_items = items
        self.stat_current.update_value(str(len(items)))

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
            cell.setColumnCount(len(headers))
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
        act_delete.setIconText("❌")

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
