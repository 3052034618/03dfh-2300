from typing import List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QFrame, QComboBox, QLineEdit, QDoubleSpinBox, QCheckBox, QGridLayout,
    QTabWidget, QGroupBox, QRadioButton, QButtonGroup, QSpinBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from .widgets import StatCard
from ..core.models import PriceItem, CategoryManager
from ..core.price_engine import PriceCalculator, PriceValidator


class BatchAdjustPage(QWidget):
    itemsUpdated = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_items: List[PriceItem] = []
        self._history = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 20)
        layout.setSpacing(15)

        title = QLabel("批量调整")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("按分类、品牌或自定义条件批量调整价格，支持预览后再应用")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_percent_tab(), "📈 百分比调整")
        self.tabs.addTab(self._build_fixed_tab(), "💵 固定金额调整")
        self.tabs.addTab(self._build_brand_tab(), "🏷️ 耗材品牌加价")
        self.tabs.addTab(self._build_name_tab(), "🏷️ 批量设置名称")
        layout.addWidget(self.tabs)

        stats_row = QHBoxLayout()
        self.stat_selected = StatCard("将被调整", "0", "#3b82f6")
        self.stat_total_before = StatCard("调整前合计", "¥0", "#64748b")
        self.stat_total_after = StatCard("调整后合计", "¥0", "#10b981")
        self.stat_diff = StatCard("价差", "+¥0", "#f59e0b")
        stats_row.addWidget(self.stat_selected)
        stats_row.addWidget(self.stat_total_before)
        stats_row.addWidget(self.stat_total_after)
        stats_row.addWidget(self.stat_diff)
        layout.addLayout(stats_row)

        preview_card = QFrame()
        preview_card.setObjectName("Card")
        p_layout = QVBoxLayout(preview_card)
        p_layout.setContentsMargins(15, 12, 15, 12)
        p_layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>调整预览</b>"))
        header.addStretch()

        self.btn_undo = QPushButton("↩ 撤销上一步")
        self.btn_undo.setEnabled(False)
        self.btn_preview = QPushButton("🔍 预览效果")
        self.btn_apply = QPushButton("✓ 应用调整")
        self.btn_apply.setObjectName("SuccessButton")
        header.addWidget(self.btn_undo)
        header.addWidget(self.btn_preview)
        header.addWidget(self.btn_apply)
        p_layout.addLayout(header)

        self.preview_table = QTableWidget()
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        p_layout.addWidget(self.preview_table, 1)

        layout.addWidget(preview_card, 1)

        self.btn_preview.clicked.connect(self._do_preview)
        self.btn_apply.clicked.connect(self._do_apply)
        self.btn_undo.clicked.connect(self._undo_last)

    def _build_percent_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        grid = QGridLayout()

        grid.addWidget(QLabel("<b>调整幅度：</b>"), 0, 0)
        self.percent_value = QDoubleSpinBox()
        self.percent_value.setRange(-90, 500)
        self.percent_value.setValue(10)
        self.percent_value.setSuffix(" %")
        self.percent_value.setSingleStep(5)
        grid.addWidget(self.percent_value, 0, 1)

        grid.addWidget(QLabel("<b>操作分类：</b>"), 1, 0)
        self.percent_category = QComboBox()
        self.percent_category.addItem("全部分类", "all")
        for cat in CategoryManager.get_all_categories():
            self.percent_category.addItem(cat, cat)
        self.percent_category.setCurrentText("光电类")
        grid.addWidget(self.percent_category, 1, 1)

        grid.addWidget(QLabel("<b>调整对象：</b>"), 2, 0)
        target_box = QFrame()
        target_layout = QVBoxLayout(target_box)
        target_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_percent_original = QCheckBox("原价")
        self.chk_percent_original.setChecked(True)
        self.chk_percent_member = QCheckBox("会员价")
        self.chk_percent_member.setChecked(True)
        self.chk_percent_doctor = QCheckBox("医生费")
        self.chk_percent_material = QCheckBox("耗材费")
        target_layout.addWidget(self.chk_percent_original)
        target_layout.addWidget(self.chk_percent_member)
        target_layout.addWidget(self.chk_percent_doctor)
        target_layout.addWidget(self.chk_percent_material)
        grid.addWidget(target_box, 2, 1)

        quick_label = QLabel("<b>快捷操作：</b>")
        grid.addWidget(quick_label, 3, 0)
        quick_box = QFrame()
        quick_layout = QHBoxLayout(quick_box)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        btn_up10 = QPushButton("光电 +10%")
        btn_up15 = QPushButton("注射 +15%")
        btn_down5 = QPushButton("清洁补水 -5%")
        btn_up10.clicked.connect(lambda: self._quick_percent("光电类", 10))
        btn_up15.clicked.connect(lambda: self._quick_percent("注射类", 15))
        btn_down5.clicked.connect(lambda: self._quick_percent("清洁补水", -5))
        quick_layout.addWidget(btn_up10)
        quick_layout.addWidget(btn_up15)
        quick_layout.addWidget(btn_down5)
        quick_layout.addStretch()
        grid.addWidget(quick_box, 3, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()

        return w

    def _build_fixed_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        grid = QGridLayout()

        grid.addWidget(QLabel("<b>调整金额：</b>"), 0, 0)
        amount_row = QHBoxLayout()
        self.fixed_mode = QComboBox()
        self.fixed_mode.addItem("下调（减少）", -1)
        self.fixed_mode.addItem("上调（增加）", 1)
        self.fixed_value = QDoubleSpinBox()
        self.fixed_value.setRange(0, 100000)
        self.fixed_value.setValue(50)
        self.fixed_value.setPrefix("¥ ")
        self.fixed_value.setSingleStep(10)
        amount_row.addWidget(self.fixed_mode)
        amount_row.addWidget(self.fixed_value)
        amount_row.addStretch()
        grid.addLayout(amount_row, 0, 1)

        grid.addWidget(QLabel("<b>操作分类：</b>"), 1, 0)
        self.fixed_category = QComboBox()
        self.fixed_category.addItem("全部分类", "all")
        for cat in CategoryManager.get_all_categories():
            self.fixed_category.addItem(cat, cat)
        self.fixed_category.setCurrentText("清洁补水")
        grid.addWidget(self.fixed_category, 1, 1)

        grid.addWidget(QLabel("<b>只调整体验价：</b>"), 2, 0)
        self.chk_experience_only = QCheckBox("仅调整名称含'体验'、'首次'、'特价'的项目")
        self.chk_experience_only.setChecked(True)
        grid.addWidget(self.chk_experience_only, 2, 1)

        grid.addWidget(QLabel("<b>调整对象：</b>"), 3, 0)
        target_box = QFrame()
        target_layout = QVBoxLayout(target_box)
        target_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_fixed_original = QCheckBox("原价")
        self.chk_fixed_original.setChecked(True)
        self.chk_fixed_member = QCheckBox("会员价")
        self.chk_fixed_member.setChecked(True)
        target_layout.addWidget(self.chk_fixed_original)
        target_layout.addWidget(self.chk_fixed_member)
        grid.addWidget(target_box, 3, 1)

        quick_box = QFrame()
        quick_layout = QHBoxLayout(quick_box)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        btn_clean = QPushButton("清洁补水体验价 -¥30")
        btn_nurse = QPushButton("皮肤护理 -¥50")
        btn_clean.clicked.connect(lambda: self._quick_fixed("清洁补水", -30, True))
        btn_nurse.clicked.connect(lambda: self._quick_fixed("皮肤护理", -50, False))
        quick_layout.addWidget(btn_clean)
        quick_layout.addWidget(btn_nurse)
        quick_layout.addStretch()

        grid.addWidget(QLabel("<b>快捷操作：</b>"), 4, 0)
        grid.addLayout(quick_layout, 4, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()
        return w

    def _build_brand_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        grid = QGridLayout()

        grid.addWidget(QLabel("<b>品牌关键词：</b>"), 0, 0)
        self.brand_keyword = QLineEdit()
        self.brand_keyword.setPlaceholderText("输入品牌名称，如：乔雅登、濡白天使、衡力...")
        grid.addWidget(self.brand_keyword, 0, 1)

        grid.addWidget(QLabel("<b>调整方式：</b>"), 1, 0)
        self.brand_mode = QComboBox()
        self.brand_mode.addItem("按固定金额加价", "fixed")
        self.brand_mode.addItem("按百分比加价", "percent")
        grid.addWidget(self.brand_mode, 1, 1)

        grid.addWidget(QLabel("<b>调整幅度：</b>"), 2, 0)
        self.brand_value = QDoubleSpinBox()
        self.brand_value.setRange(-10000, 100000)
        self.brand_value.setValue(100)
        self.brand_value.setPrefix("¥ ")
        grid.addWidget(self.brand_value, 2, 1)

        self.brand_mode.currentIndexChanged.connect(self._on_brand_mode_change)

        grid.addWidget(QLabel("<b>匹配范围：</b>"), 3, 0)
        match_box = QFrame()
        match_layout = QVBoxLayout(match_box)
        match_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_brand_material = QCheckBox("耗材费")
        self.chk_brand_material.setChecked(True)
        self.chk_brand_field = QCheckBox("耗材品牌字段匹配")
        self.chk_brand_field.setChecked(True)
        self.chk_brand_name = QCheckBox("项目名称包含匹配")
        self.chk_brand_remark = QCheckBox("备注包含匹配")
        match_layout.addWidget(self.chk_brand_material)
        match_layout.addWidget(self.chk_brand_field)
        match_layout.addWidget(self.chk_brand_name)
        match_layout.addWidget(self.chk_brand_remark)
        grid.addWidget(match_box, 3, 1)

        quick_grid = QFrame()
        q_layout = QHBoxLayout(quick_grid)
        q_layout.setContentsMargins(0, 0, 0, 0)
        brands = ["乔雅登", "濡白天使", "衡力", "保妥适", "艾莉薇", "嗨体"]
        for b in brands:
            btn = QPushButton(f"{b} +¥100")
            btn.clicked.connect(lambda _, x=b: self._quick_brand(x, 100, True))
            q_layout.addWidget(btn)
        q_layout.addStretch()

        grid.addWidget(QLabel("<b>常用品牌快捷：</b>"), 4, 0)
        grid.addLayout(q_layout, 4, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        brand_list_card = QFrame()
        brand_list_card.setObjectName("Card")
        bl_layout = QVBoxLayout(brand_list_card)
        bl_layout.setContentsMargins(12, 10, 12, 10)
        bl_layout.addWidget(QLabel("<b>当前识别到的耗材品牌：</b>"))
        self.brand_list_label = QLabel("暂无数据，请先导入项目")
        self.brand_list_label.setWordWrap(True)
        self.brand_list_label.setStyleSheet("color: #64748b; padding-top: 5px;")
        bl_layout.addWidget(self.brand_list_label)
        layout.addWidget(brand_list_card)

        layout.addStretch()
        return w

    def _build_name_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        grid = QGridLayout()

        grid.addWidget(QLabel("<b>操作模式：</b>"), 0, 0)
        self.name_mode = QComboBox()
        self.name_mode.addItem("设置前台展示名 = 项目名称", "display_same")
        self.name_mode.addItem("设置内部核算名 = 项目名称", "internal_same")
        self.name_mode.addItem("批量添加前缀", "prefix")
        self.name_mode.addItem("批量添加后缀", "suffix")
        self.name_mode.addItem("查找替换", "replace")
        grid.addWidget(self.name_mode, 0, 1)

        grid.addWidget(QLabel("<b>目标分类：</b>"), 1, 0)
        self.name_category = QComboBox()
        self.name_category.addItem("全部分类", "all")
        for cat in CategoryManager.get_all_categories():
            self.name_category.addItem(cat, cat)
        grid.addWidget(self.name_category, 1, 1)

        grid.addWidget(QLabel("<b>作用字段：</b>"), 2, 0)
        name_target = QFrame()
        nt_layout = QVBoxLayout(name_target)
        nt_layout.setContentsMargins(0, 0, 0, 0)
        self.chk_name_display = QCheckBox("前台展示名")
        self.chk_name_display.setChecked(True)
        self.chk_name_internal = QCheckBox("内部核算名")
        self.chk_name_original = QCheckBox("项目名称")
        nt_layout.addWidget(self.chk_name_display)
        nt_layout.addWidget(self.chk_name_internal)
        nt_layout.addWidget(self.chk_name_original)
        grid.addWidget(name_target, 2, 1)

        grid.addWidget(QLabel("<b>参数设置：</b>"), 3, 0)
        param_box = QFrame()
        param_layout = QGridLayout(param_box)
        param_layout.setContentsMargins(0, 0, 0, 0)
        param_layout.addWidget(QLabel("前缀/后缀/查找："), 0, 0)
        self.name_param1 = QLineEdit()
        param_layout.addWidget(self.name_param1, 0, 1)
        param_layout.addWidget(QLabel("替换为："), 1, 0)
        self.name_param2 = QLineEdit()
        param_layout.addWidget(self.name_param2, 1, 1)
        grid.addWidget(param_box, 3, 1)

        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch()
        return w

    def set_items(self, items: List[PriceItem]):
        self.current_items = items
        self._history = []
        self.btn_undo.setEnabled(False)
        self._refresh_brand_list()
        self._build_preview_table(self.current_items, {})

    def _refresh_brand_list(self):
        brands = set()
        for it in self.current_items:
            if it.material_brand:
                brands.add(it.material_brand.strip())
        if brands:
            self.brand_list_label.setText("、".join(sorted(brands)) + f"（共 {len(brands)} 个）")
        else:
            self.brand_list_label.setText("暂无已识别品牌，您仍可通过关键词匹配项目名称或备注")

    def _on_brand_mode_change(self):
        mode = self.brand_mode.currentData()
        if mode == "percent":
            self.brand_value.setRange(-90, 500)
            self.brand_value.setSuffix(" %")
            self.brand_value.setPrefix("")
            self.brand_value.setValue(10)
        else:
            self.brand_value.setRange(-10000, 100000)
            self.brand_value.setPrefix("¥ ")
            self.brand_value.setSuffix("")
            self.brand_value.setValue(100)

    def _quick_percent(self, category: str, percent: float):
        self.tabs.setCurrentIndex(0)
        self.percent_category.setCurrentText(category)
        self.percent_value.setValue(percent)
        self._do_preview()

    def _quick_fixed(self, category: str, amount: float, experience_only: bool):
        self.tabs.setCurrentIndex(1)
        self.fixed_category.setCurrentText(category)
        mode_idx = 0 if amount < 0 else 1
        self.fixed_mode.setCurrentIndex(mode_idx)
        self.fixed_value.setValue(abs(amount))
        self.chk_experience_only.setChecked(experience_only)
        self._do_preview()

    def _quick_brand(self, keyword: str, amount: float, is_fixed: bool):
        self.tabs.setCurrentIndex(2)
        self.brand_keyword.setText(keyword)
        self.brand_mode.setCurrentIndex(0 if is_fixed else 1)
        self.brand_value.setValue(amount)
        self._do_preview()

    def _clone_items(self, items: List[PriceItem]) -> List[PriceItem]:
        return [PriceItem(**{k: getattr(it, k) for k in PriceItem.__dataclass_fields__}) for it in items]

    def _get_filter_func(self, tab_idx: int):
        if tab_idx == 0:
            cat = self.percent_category.currentData()
            if cat == "all":
                return None
            return lambda x: x.category == cat

        elif tab_idx == 1:
            cat = self.fixed_category.currentData()
            exp_only = self.chk_experience_only.isChecked()
            keywords = ["体验", "首次", "特价", "特惠", "活动"]

            def _f(x):
                if cat != "all" and x.category != cat:
                    return False
                if exp_only:
                    text = (x.name or "") + (x.remark or "") + (x.display_name or "")
                    if not any(k in text for k in keywords):
                        return False
                return True
            return _f

        elif tab_idx == 2:
            keyword = self.brand_keyword.text().strip()
            check_field = self.chk_brand_field.isChecked()
            check_name = self.chk_brand_name.isChecked()
            check_remark = self.chk_brand_remark.isChecked()

            def _f(x):
                if not keyword:
                    return False
                if check_field and keyword in (x.material_brand or ""):
                    return True
                if check_name and keyword in (x.name or ""):
                    return True
                if check_remark and keyword in (x.remark or ""):
                    return True
                return False
            return _f

        elif tab_idx == 3:
            cat = self.name_category.currentData()
            if cat == "all":
                return None
            return lambda x: x.category == cat

        return None

    def _do_preview(self):
        if not self.current_items:
            QMessageBox.warning(self, "提示", "请先导入项目数据")
            return

        tab_idx = self.tabs.currentIndex()
        test_items = self._clone_items(self.current_items)
        filter_func = self._get_filter_func(tab_idx)

        affected_ids = set()
        before_total = 0.0
        after_total = 0.0

        if tab_idx == 0:
            fields = []
            if self.chk_percent_original.isChecked():
                fields.append("original_price")
            if self.chk_percent_member.isChecked():
                fields.append("member_price")
            if self.chk_percent_doctor.isChecked():
                fields.append("doctor_fee")
            if self.chk_percent_material.isChecked():
                fields.append("material_fee")
            if not fields:
                QMessageBox.warning(self, "提示", "请至少选择一个调整对象")
                return
            PriceCalculator.adjust_by_percentage(test_items, self.percent_value.value(), filter_func, fields)

        elif tab_idx == 1:
            fields = []
            if self.chk_fixed_original.isChecked():
                fields.append("original_price")
            if self.chk_fixed_member.isChecked():
                fields.append("member_price")
            if not fields:
                QMessageBox.warning(self, "提示", "请至少选择一个调整对象")
                return
            amount = self.fixed_mode.currentData() * self.fixed_value.value()
            PriceCalculator.adjust_by_fixed_amount(test_items, amount, filter_func, fields)

        elif tab_idx == 2:
            keyword = self.brand_keyword.text().strip()
            if not keyword:
                QMessageBox.warning(self, "提示", "请输入品牌关键词")
                return
            is_percent = self.brand_mode.currentData() == "percent"
            PriceCalculator.adjust_material_fee_by_brand(
                test_items, keyword, self.brand_value.value(), is_percent
            )

        elif tab_idx == 3:
            mode = self.name_mode.currentData()
            targets = []
            if self.chk_name_display.isChecked():
                targets.append("display_name")
            if self.chk_name_internal.isChecked():
                targets.append("internal_name")
            if self.chk_name_original.isChecked():
                targets.append("name")
            if not targets:
                QMessageBox.warning(self, "提示", "请至少选择一个作用字段")
                return

            p1 = self.name_param1.text()
            p2 = self.name_param2.text()
            for item in test_items:
                if filter_func and not filter_func(item):
                    continue
                for field in targets:
                    old_val = getattr(item, field) or ""
                    new_val = old_val
                    if mode == "display_same":
                        new_val = item.name
                    elif mode == "internal_same":
                        new_val = item.name
                    elif mode == "prefix":
                        new_val = p1 + (old_val or item.name)
                    elif mode == "suffix":
                        new_val = (old_val or item.name) + p1
                    elif mode == "replace":
                        new_val = (old_val or item.name).replace(p1, p2)
                    setattr(item, field, new_val)
                    affected_ids.add(item.id)

        for orig, new in zip(self.current_items, test_items):
            if filter_func and tab_idx < 3:
                _pass = filter_func(orig)
            else:
                _pass = tab_idx < 3
            if tab_idx == 2:
                keyword = self.brand_keyword.text().strip()
                _pass = (
                    (self.chk_brand_field.isChecked() and keyword in (orig.material_brand or "")) or
                    (self.chk_brand_name.isChecked() and keyword in (orig.name or "")) or
                    (self.chk_brand_remark.isChecked() and keyword in (orig.remark or ""))
                ) if keyword else False

            if _pass or (tab_idx == 3 and orig.id in affected_ids):
                affected_ids.add(orig.id)
            before_total += orig.original_price + orig.member_price
            after_total += new.original_price + new.member_price

        self._preview_items = test_items
        self._affected_ids = affected_ids
        self.stat_selected.update_value(str(len(affected_ids)))
        self.stat_total_before.update_value(f"¥{before_total:,.0f}")
        self.stat_total_after.update_value(f"¥{after_total:,.0f}")
        diff = after_total - before_total
        diff_color = "#10b981" if diff > 0 else ("#ef4444" if diff < 0 else "#64748b")
        diff_sign = "+" if diff > 0 else ""
        self.stat_diff.update_value(f"{diff_sign}¥{diff:,.0f}")
        self.stat_diff.value_label.setStyleSheet(f"color: {diff_color};")

        self._build_preview_table(test_items, affected_ids)

    def _build_preview_table(self, items: List[PriceItem], affected_ids: set):
        self.preview_table.setColumnCount(10)
        headers = ["变化", "项目名称", "分类", "原价(前)", "原价(后)",
                  "会员价(前)", "会员价(后)", "耗材费(前)", "耗材费(后)", "备注"]
        self.preview_table.setHorizontalHeaderLabels(headers)

        if affected_ids:
            display_items = [(i, o) for i, o in zip(items, self.current_items) if i.id in affected_ids]
        else:
            display_items = list(zip(items, self.current_items))

        self.preview_table.setRowCount(len(display_items))

        for row, (new, old) in enumerate(display_items):
            changed = (
                new.original_price != old.original_price or
                new.member_price != old.member_price or
                new.material_fee != old.material_fee or
                new.display_name != old.display_name or
                new.internal_name != old.internal_name or
                new.name != old.name
            )
            status_text = "✨ 变化" if changed else "-"
            status_color = "#3b82f6" if changed else "#94a3b8"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QBrush(QColor(status_color)))
            status_item.setFont(QFont("", 9, QFont.Bold))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.preview_table.setItem(row, 0, status_item)

            fields = [
                (1, new.name, old.name, False),
                (2, new.category, old.category, False),
                (3, old.original_price, old.original_price, True),
                (4, new.original_price, old.original_price, True),
                (5, old.member_price, old.member_price, True),
                (6, new.member_price, old.member_price, True),
                (7, old.material_fee, old.material_fee, True),
                (8, new.material_fee, old.material_fee, True),
                (9, new.remark, old.remark, False),
            ]
            for col, val, old_val, is_price in fields:
                if is_price:
                    text = f"¥{val:,.2f}" if val > 0 else "-"
                else:
                    text = str(val or "-")
                cell = QTableWidgetItem(text)
                if col >= 3 and is_price:
                    cell.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                if col in [4, 6, 8] and val != old_val and is_price:
                    if val > old_val:
                        cell.setForeground(QBrush(QColor("#10b981")))
                    elif val < old_val:
                        cell.setForeground(QBrush(QColor("#ef4444")))
                    cell.setBackground(QBrush(QColor("#fef9c3")))
                    cell.setFont(QFont("", 9, QFont.Bold))
                if col in [1, 9] and val != old_val:
                    cell.setBackground(QBrush(QColor("#dbeafe")))
                self.preview_table.setItem(row, col, cell)

        for col in range(10):
            self.preview_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    def _do_apply(self):
        if not hasattr(self, "_preview_items"):
            QMessageBox.warning(self, "提示", "请先点击预览查看调整效果")
            return

        reply = QMessageBox.question(
            self, "确认应用",
            f"将对 {len(self._affected_ids)} 个项目应用调整，此操作可通过'撤销上一步'回退。\n\n是否确认？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._history.append(self._clone_items(self.current_items))
        self.btn_undo.setEnabled(True)
        self.current_items = self._preview_items
        self._preview_items = self._clone_items(self.current_items)

        for it in self.current_items:
            it.update_timestamp()

        PriceValidator.run_all_validations(self.current_items)
        self.itemsUpdated.emit(self.current_items)
        QMessageBox.information(self, "调整完成", f"已成功调整 {len(self._affected_ids)} 个项目")
        self._build_preview_table(self.current_items, set())

    def _undo_last(self):
        if not self._history:
            return
        reply = QMessageBox.question(
            self, "确认撤销",
            f"将撤销最近一次批量调整，恢复到上一个状态。是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.current_items = self._history.pop()
        self.btn_undo.setEnabled(len(self._history) > 0)
        self.itemsUpdated.emit(self.current_items)
        self._build_preview_table(self.current_items, set())
        self.stat_selected.update_value("0")
        self.stat_total_before.update_value("¥0")
        self.stat_total_after.update_value("¥0")
        self.stat_diff.update_value("+¥0")
        self.stat_diff.value_label.setStyleSheet("color: #f59e0b;")
        QMessageBox.information(self, "已撤销", "已恢复到上一状态")
