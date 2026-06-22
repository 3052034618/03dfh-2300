from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QDialog, QDialogButtonBox, QComboBox, QRadioButton, QButtonGroup,
    QFrame, QFileDialog, QScrollArea, QCheckBox, QGridLayout, QGroupBox,
    QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from .widgets import DropZone, StatCard
from ..core.models import PriceItem
from ..core.data_manager import ExcelImporter, MappingTemplateManager
from ..core.price_engine import PriceValidator, ConflictResolver


FIELD_LABELS = [
    ("name", "项目名称（必填）", True),
    ("display_name", "前台展示名", False),
    ("internal_name", "内部核算名", False),
    ("category", "分类", False),
    ("original_price", "原价（必填）", True),
    ("member_price", "会员价", False),
    ("doctor_fee", "医生费", False),
    ("material_fee", "耗材费", False),
    ("material_brand", "耗材品牌", False),
    ("cost_price", "成本价", False),
    ("remark", "备注", False),
]


class FieldMappingDialog(QDialog):
    """字段映射确认对话框：让用户手动匹配 Excel 列与价目表字段，支持门店模板。"""
    mappingConfirmed = Signal(dict)

    def __init__(self, headers: List[str], preview_rows: List[List[str]],
                 auto_mapping: Dict[str, int],
                 templates: Optional[List[Dict[str, Any]]] = None,
                 matched_template: Optional[Dict[str, Any]] = None,
                 match_score: float = 0.0,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("字段映射确认 - 请核对 Excel 列对应关系")
        self.setMinimumSize(860, 640)
        self.headers = headers
        self.preview_rows = preview_rows
        self._combo_map: Dict[str, QComboBox] = {}
        self._templates = templates or []
        self._matched_template = matched_template
        self._match_score = match_score

        layout = QVBoxLayout(self)

        # --- 顶部：模板选择 + 智能匹配提示
        template_bar = QFrame()
        template_bar.setObjectName("Card")
        tb_layout = QHBoxLayout(template_bar)
        tb_layout.setContentsMargins(12, 10, 12, 10)

        tb_layout.addWidget(QLabel("<b>🏪 门店模板：</b>"))
        self.cmb_template = QComboBox()
        self.cmb_template.addItem("（不使用模板）", "")
        for tpl in self._templates:
            name = tpl.get("store_name", "")
            cnt = tpl.get("use_count", 0)
            self.cmb_template.addItem(f"{name}  (已用 {cnt} 次)", name)
        self.cmb_template.setMinimumWidth(220)
        tb_layout.addWidget(self.cmb_template)

        self.btn_apply_template = QPushButton("套用模板")
        self.btn_apply_template.setToolTip("将所选模板的映射应用到下方")
        tb_layout.addWidget(self.btn_apply_template)

        self.btn_save_template = QPushButton("💾 保存为门店模板")
        self.btn_save_template.setObjectName("PrimaryButton")
        tb_layout.addWidget(self.btn_save_template)
        tb_layout.addStretch()

        self.template_hint = QLabel("")
        self.template_hint.setStyleSheet(
            "padding: 4px 10px; border-radius: 4px; font-size: 9pt;"
        )
        tb_layout.addWidget(self.template_hint)

        layout.addWidget(template_bar)

        # --- 匹配度提示横幅
        self.match_banner = QLabel("")
        self.match_banner.setWordWrap(True)
        self.match_banner.setStyleSheet(
            "padding: 10px 14px; border-radius: 6px; font-size: 10pt;"
        )
        layout.addWidget(self.match_banner)

        # --- 预览表（显示表头与前几行，让运营直观判断）
        preview_group = QGroupBox("📋 Excel 内容预览（前几行）")
        pv_layout = QVBoxLayout(preview_group)
        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        pv_layout.addWidget(self.preview_table)
        preview_group.setMaximumHeight(180)
        layout.addWidget(preview_group)

        # --- 字段映射区
        map_group = QGroupBox("🔗 字段映射（左侧是价目表字段 → 右侧选择 Excel 列）")
        map_layout = QGridLayout(map_group)
        map_layout.addWidget(QLabel("<b>价目表字段</b>"), 0, 0)
        map_layout.addWidget(QLabel("<b>对应 Excel 列</b>"), 0, 1)
        options = ["（不导入该字段）"] + headers
        for row, (field_key, field_label, required) in enumerate(FIELD_LABELS, start=1):
            if required:
                lbl_text = f"{field_label}  <span style='color:#dc2626'>*必填</span>"
            else:
                lbl_text = field_label
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("padding: 4px 0;")
            map_layout.addWidget(lbl, row, 0)
            combo = QComboBox()
            combo.addItems(options)
            # 自动匹配值（先用 auto_mapping，若有模板会被覆盖）
            default_idx = 0
            if field_key in auto_mapping and auto_mapping[field_key] < len(headers):
                default_idx = auto_mapping[field_key] + 1
            if default_idx >= combo.count():
                default_idx = 0
            combo.setCurrentIndex(default_idx)
            self._combo_map[field_key] = combo
            map_layout.addWidget(combo, row, 1)
        layout.addWidget(map_group, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("✓ 确认导入")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 连接信号
        self.btn_apply_template.clicked.connect(self._on_apply_template)
        self.btn_save_template.clicked.connect(self._on_save_template)

        self._fill_preview()
        self._apply_matched_template_if_high()
        self._update_match_banner()

    def _fill_preview(self):
        self.preview_table.setColumnCount(len(self.headers))
        self.preview_table.setHorizontalHeaderLabels(self.headers)
        self.preview_table.setRowCount(len(self.preview_rows))
        for r, row in enumerate(self.preview_rows):
            for c, val in enumerate(row):
                if c >= len(self.headers):
                    break
                cell = QTableWidgetItem(str(val))
                self.preview_table.setItem(r, c, cell)
        for col in range(len(self.headers)):
            self.preview_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)

    def _update_match_banner(self):
        """根据当前匹配度显示不同颜色的提示横幅。"""
        if not self._matched_template or self._match_score <= 0:
            self.match_banner.setText(
                "💡 未找到匹配的门店模板，系统已按列名做了自动匹配。"
                "请核对下方映射，确认无误后导入，或保存为新模板以便下次使用。"
            )
            self.match_banner.setStyleSheet(
                "padding: 10px 14px; background: #f8fafc; color: #475569;"
                " border: 1px solid #e2e8f0; border-radius: 6px; font-size: 10pt;"
            )
            self.template_hint.setText("")
            return

        store = self._matched_template.get("store_name", "")
        score_pct = int(self._match_score * 100)
        if self._match_score >= 0.85:
            self.match_banner.setText(
                f"✅ 高度匹配「{store}」门店模板（相似度 {score_pct}%），"
                f"已自动套用。建议快速核对后直接确认导入。"
            )
            self.match_banner.setStyleSheet(
                "padding: 10px 14px; background: #ecfdf5; color: #065f46;"
                " border: 1px solid #a7f3d0; border-radius: 6px; font-size: 10pt;"
            )
            self.template_hint.setText("✅ 自动套用")
            self.template_hint.setStyleSheet(
                "padding: 4px 10px; background: #d1fae5; color: #065f46;"
                " border-radius: 4px; font-size: 9pt; font-weight: 600;"
            )
        elif self._match_score >= 0.5:
            self.match_banner.setText(
                f"⚠️ 可能匹配「{store}」门店模板（相似度 {score_pct}%），"
                f"表头有一定变化，请仔细核对列对应关系后再导入。"
            )
            self.match_banner.setStyleSheet(
                "padding: 10px 14px; background: #fffbeb; color: #92400e;"
                " border: 1px solid #fcd34d; border-radius: 6px; font-size: 10pt;"
            )
            self.template_hint.setText(f"⚠️ {score_pct}% 相似")
            self.template_hint.setStyleSheet(
                "padding: 4px 10px; background: #fef3c7; color: #92400e;"
                " border-radius: 4px; font-size: 9pt; font-weight: 600;"
            )
            # 中等相似度也自动套用，但是用黄色提醒
        else:
            self.match_banner.setText(
                f"🔍 找到低相似度模板「{store}」（{score_pct}%），"
                f"建议手动确认映射或使用其他模板。"
            )
            self.match_banner.setStyleSheet(
                "padding: 10px 14px; background: #fef2f2; color: #991b1b;"
                " border: 1px solid #fecaca; border-radius: 6px; font-size: 10pt;"
            )
            self.template_hint.setText(f"🔍 {score_pct}%")
            self.template_hint.setStyleSheet(
                "padding: 4px 10px; background: #fee2e2; color: #991b1b;"
                " border-radius: 4px; font-size: 9pt;"
            )

    def _apply_mapping_from_dict(self, mapping: Dict[str, int]):
        """把一个 mapping dict 应用到下拉框。"""
        for field_key, combo in self._combo_map.items():
            col_idx = mapping.get(field_key, -1)
            if col_idx >= 0 and col_idx < len(self.headers):
                combo.setCurrentIndex(col_idx + 1)  # +1 因为首项是"不导入"
            else:
                combo.setCurrentIndex(0)

    def _apply_matched_template_if_high(self):
        """如果有高度/中度匹配的模板，自动套用。"""
        if self._matched_template and self._match_score >= 0.5:
            tpl_mapping = self._matched_template.get("mapping", {})
            self._apply_mapping_from_dict(tpl_mapping)
            # 同步下拉选中到对应模板名
            store = self._matched_template.get("store_name", "")
            for i in range(self.cmb_template.count()):
                if self.cmb_template.itemData(i) == store:
                    self.cmb_template.setCurrentIndex(i)
                    break

    def _on_apply_template(self):
        """用户点击「套用模板」按钮。"""
        store_name = self.cmb_template.currentData()
        if not store_name:
            QMessageBox.information(self, "提示", "请先选择一个门店模板")
            return
        tpl = next((t for t in self._templates if t.get("store_name") == store_name), None)
        if not tpl:
            return
        self._apply_mapping_from_dict(tpl.get("mapping", {}))
        QMessageBox.information(
            self, "已套用",
            f"已套用「{store_name}」门店模板的字段映射，请核对后确认。"
        )

    def _on_save_template(self):
        """保存当前映射为门店模板。"""
        current_mapping = self._collect_mapping()
        if not current_mapping:
            QMessageBox.warning(self, "提示", "当前没有可保存的映射配置")
            return

        default_name = ""
        if self._matched_template:
            default_name = self._matched_template.get("store_name", "")

        name, ok = QInputDialog.getText(
            self, "保存为门店模板",
            "请输入门店名称（如：朝阳门店、西单店）：",
            text=default_name
        )
        if not ok or not name.strip():
            return

        # 检查是否覆盖
        existing = next((t for t in self._templates
                         if t.get("store_name", "").strip() == name.strip()), None)
        if existing:
            reply = QMessageBox.question(
                self, "覆盖确认",
                f"已存在「{name.strip()}」门店模板，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # 保存（由调用方实际持久化，这里只发信号/存到属性里）
        self._pending_save_template = {
            "store_name": name.strip(),
            "headers": list(self.headers),
            "mapping": dict(current_mapping),
        }
        QMessageBox.information(
            self, "已保存",
            f"「{name.strip()}」门店模板已保存。\n"
            f"下次导入相似表头的表格时会自动套用。"
        )
        # 刷新模板下拉
        self._templates = [t for t in self._templates
                           if t.get("store_name") != name.strip()]
        self._templates.insert(0, self._pending_save_template)
        self.cmb_template.clear()
        self.cmb_template.addItem("（不使用模板）", "")
        for tpl in self._templates:
            nm = tpl.get("store_name", "")
            cnt = tpl.get("use_count", 0)
            self.cmb_template.addItem(f"{nm}  (已用 {cnt} 次)", nm)
        for i in range(self.cmb_template.count()):
            if self.cmb_template.itemData(i) == name.strip():
                self.cmb_template.setCurrentIndex(i)
                break

    def _collect_mapping(self) -> Dict[str, int]:
        """从下拉框收集当前的映射配置。"""
        mapping: Dict[str, int] = {}
        for field_key, combo in self._combo_map.items():
            idx = combo.currentIndex()
            if idx > 0:
                mapping[field_key] = idx - 1
        return mapping

    def _on_confirm(self):
        mapping = self._collect_mapping()
        # 校验必填
        missing = []
        for field_key, label, required in FIELD_LABELS:
            if required and field_key not in mapping:
                missing.append(label)
        if missing:
            QMessageBox.warning(
                self, "缺少必填字段",
                "以下必填字段未匹配 Excel 列：\n\n  • " + "\n  • ".join(missing) +
                "\n\n请至少为必填字段选择对应的 Excel 列。"
            )
            return
        # 若有要保存的模板，把模板信息也一起传出去
        if hasattr(self, "_pending_save_template") and self._pending_save_template:
            self.mappingConfirmed.emit({
                "mapping": mapping,
                "save_template": self._pending_save_template,
            })
        else:
            # 如果是从已有的模板套用的，传回门店名以便 touch
            store_name = self.cmb_template.currentData()
            self.mappingConfirmed.emit({
                "mapping": mapping,
                "store_name": store_name,
            })
        self.accept()


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

    def __init__(self, template_manager: Optional[MappingTemplateManager] = None, parent=None):
        super().__init__(parent)
        self.current_items: List[PriceItem] = []
        self.template_manager = template_manager
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
        # 第一步：只读表头+前几行，用于字段映射确认
        headers, preview_rows, warnings = ExcelImporter.inspect_file(file_path)
        if not headers:
            QMessageBox.critical(self, "导入失败", "\n".join(warnings) if warnings else "无法读取文件表头")
            return

        # 自动匹配默认 mapping
        auto_mapping = ExcelImporter._map_columns(headers)

        # 模板匹配（如果有模板管理器）
        templates = []
        matched_template = None
        match_score = 0.0
        if self.template_manager is not None:
            templates = self.template_manager.list_templates()
            matched_template, match_score = self.template_manager.find_best_match(headers)

        # 第二步：弹字段映射确认对话框
        dlg = FieldMappingDialog(
            headers, preview_rows, auto_mapping,
            templates=templates,
            matched_template=matched_template,
            match_score=match_score,
            parent=self
        )
        confirmed_result = {}
        dlg.mappingConfirmed.connect(lambda m: confirmed_result.update(m))
        if dlg.exec() != QDialog.Accepted or not confirmed_result:
            return  # 用户取消

        confirmed_mapping = confirmed_result.get("mapping", {})
        if not confirmed_mapping:
            return

        # 保存模板（如果用户点了保存）
        save_tpl = confirmed_result.get("save_template")
        if save_tpl and self.template_manager is not None:
            self.template_manager.save_template(
                save_tpl["store_name"],
                save_tpl["headers"],
                save_tpl["mapping"]
            )
        # 或者更新使用次数
        used_store = confirmed_result.get("store_name")
        if used_store and self.template_manager is not None:
            self.template_manager.touch_template(used_store)

        # 第三步：按确认后的 mapping 正式导入
        items, import_warnings = ExcelImporter.import_file(file_path, col_mapping=confirmed_mapping)
        if not items:
            QMessageBox.critical(self, "导入失败", "\n".join(import_warnings) if import_warnings else "未识别到有效数据")
            return

        self.current_items = items

        all_warnings = warnings + import_warnings
        if all_warnings:
            QMessageBox.warning(self, "导入提示", "\n".join(all_warnings))

        validations = PriceValidator.run_all_validations(items)
        conflicts = validations["price_conflicts"]
        errors = validations["all_errors"]

        categories = set(it.category for it in items)

        self.stat_total.update_value(str(len(items)))
        self.stat_categories.update_value(str(len(categories)))
        self.stat_conflicts.update_value(str(len(conflicts)))
        self.stat_errors.update_value(str(len(errors)))

        self._refresh_preview_table()
        self.preview_card.setVisible(True)

        filename = file_path.replace("\\", "/").split("/")[-1]
        self.drop_zone.text_label.setText(f"已导入: {filename}")

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
