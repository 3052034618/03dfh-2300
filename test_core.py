#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心功能自测脚本 - 验证数据模型、价格引擎、备份功能
"""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.models import PriceItem, CategoryManager
from app.core.price_engine import PriceCalculator, PriceValidator, ConflictResolver
from app.core.data_manager import ExcelImporter, BackupManager, DataStore


def test_models():
    print("🔧 测试数据模型...", end=" ")
    item = PriceItem(
        name="热玛吉四代 900发",
        category="光电类",
        original_price=12800,
        member_price=9800,
        doctor_fee=3000,
        material_fee=1500,
        cost_price=500
    )
    assert item.total_cost == 5000, f"总成本计算错误: {item.total_cost}"
    assert item.member_profit == 4800, f"利润计算错误: {item.member_profit}"
    assert len(item.validate()) == 0, f"不应有校验错误: {item.validate()}"

    item_bad = PriceItem(name="测试", original_price=100, member_price=200)
    errors = item_bad.validate()
    assert len(errors) > 0, "应检测到会员价高于原价"
    print("✅")


def test_category():
    print("🔧 测试分类识别...", end=" ")
    assert CategoryManager.detect_category("热玛吉") == "光电类"
    assert CategoryManager.detect_category("乔雅登玻尿酸") == "注射类"
    assert CategoryManager.detect_category("双眼皮切开") == "手术类"
    assert CategoryManager.detect_category("小气泡清洁") == "清洁补水"
    assert CategoryManager.detect_category("SPA全身按摩") == "皮肤护理"
    assert CategoryManager.detect_category("其他项目") == "其他"
    print("✅")


def test_price_calculator():
    print("🔧 测试价格计算...", end=" ")
    items = [
        PriceItem(name="热玛吉", category="光电类", original_price=10000, member_price=8000),
        PriceItem(name="光子嫩肤", category="光电类", original_price=1000, member_price=800),
        PriceItem(name="小气泡", category="清洁补水", original_price=200, member_price=99),
    ]

    PriceCalculator.adjust_光电_items(items, 10)
    assert items[0].original_price == 11000, f"百分比计算错误: {items[0].original_price}"
    assert items[1].original_price == 1100
    assert items[2].original_price == 200, "清洁补水不应被光电类调整影响"

    PriceCalculator.adjust_清洁补水_items(items, 30)
    assert items[2].original_price == 170, f"固定金额计算错误: {items[2].original_price}"
    assert items[2].member_price == 69

    item_brand = PriceItem(name="乔雅登雅致", material_fee=3000, material_brand="乔雅登")
    PriceCalculator.adjust_material_fee_by_brand([item_brand], "乔雅登", 100)
    assert item_brand.material_fee == 3100, f"品牌加价错误: {item_brand.material_fee}"
    print("✅")


def test_validator():
    print("🔧 测试价格校验...", end=" ")
    items = [
        PriceItem(id="1", name="正常项目", original_price=2000, member_price=1500,
                 doctor_fee=300, material_fee=200),
        PriceItem(id="2", name="会员价过高", original_price=1000, member_price=2000),
        PriceItem(id="3", name="低于成本", original_price=100, member_price=80,
                 doctor_fee=300, material_fee=200),
        PriceItem(id="4", name="重复项目", original_price=500),
        PriceItem(id="5", name="重复项目", original_price=600),
    ]

    results = PriceValidator.run_all_validations(items)
    assert len(results["member_above_original"]) == 1
    assert len(results["below_cost"]) == 2, f"原价和会员价都应检测到，实际：{len(results['below_cost'])}"
    assert len(results["duplicate_names"]) == 1
    assert len(results["price_conflicts"]) == 1

    can_save, errors = PriceValidator.can_save(items)
    assert not can_save, "应检测到无法保存的错误"
    assert len(errors) >= 3, f"校验错误数量不足，实际：{len(errors)}"
    print("✅")


def test_conflict_resolver():
    print("🔧 测试冲突解决...", end=" ")
    items = [
        PriceItem(id="a", name="重复项目", original_price=500, member_price=400, remark="A备注"),
        PriceItem(id="b", name="重复项目", original_price=800, member_price=600, display_name="展示B"),
        PriceItem(id="c", name="重复项目", original_price=300, member_price=200),
    ]

    highest = ConflictResolver.resolve_keep_highest_price(items)
    assert highest.original_price == 800

    lowest = ConflictResolver.resolve_keep_lowest_price(items)
    assert lowest.original_price == 300

    merged = ConflictResolver.merge_items(highest, [items[0], items[2]])
    assert merged.display_name == "展示B"
    assert merged.remark == "A备注"
    assert merged.is_conflict == False
    print("✅")


def test_data_manager():
    print("🔧 测试数据管理...", end=" ")
    test_dir = tempfile.mkdtemp()
    try:
        data_dir = os.path.join(test_dir, "data")
        backup_dir = os.path.join(test_dir, "backups")

        store = DataStore(data_dir, backup_dir)

        items = [
            PriceItem(name="测试项目A", original_price=1000, member_price=800),
            PriceItem(name="测试项目B", original_price=2000, member_price=1500),
        ]
        store.set_items(items)
        ok, errors = store.save(snapshot_name="测试快照")
        assert ok, f"保存失败: {errors}"

        snapshots = store.backup_manager.list_snapshots()
        assert len(snapshots) >= 1

        snap_id = snapshots[0]["id"]
        loaded = store.backup_manager.load_snapshot(snap_id)
        assert loaded is not None
        assert len(loaded) == 2

        items2 = [PriceItem(name="新项目", original_price=500)]
        store.set_items(items2)
        store.save(snapshot_name="第二个快照")

        rolled = store.backup_manager.rollback_to(snap_id)
        assert rolled is not None
        assert len(rolled) == 2

        items[0].original_price = 1500
        store.set_items(items)
        ok, _ = store.save()
        assert ok

        reloaded = store.load()
        assert len(reloaded) == 2
        assert reloaded[0].original_price == 1500

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    print("✅")


def test_excel():
    print("🔧 测试Excel导入导出...", end=" ")
    test_dir = tempfile.mkdtemp()
    try:
        items = [
            PriceItem(
                name="热玛吉四代", display_name="热玛吉抗衰", internal_name="TMJ-001",
                category="光电类", original_price=12800, member_price=9800,
                doctor_fee=3000, material_fee=1500, material_brand="Thermage",
                cost_price=500, remark="含下颌缘"
            ),
            PriceItem(
                name="乔雅登雅致", display_name="乔雅登填充", internal_name="QYD-001",
                category="注射类", original_price=6800, member_price=5800,
                doctor_fee=800, material_fee=3500, material_brand="乔雅登",
                cost_price=500, remark="单支不稀释"
            ),
        ]

        excel_path = os.path.join(test_dir, "test_export.xlsx")
        ExcelImporter.export_items(items, excel_path, include_internal=True)
        assert os.path.exists(excel_path), "导出文件不存在"
        assert os.path.getsize(excel_path) > 100

        imported, warnings = ExcelImporter.import_file(excel_path)
        assert len(imported) == 2, f"导入数量错误: {len(imported)}"
        assert imported[0].name == "热玛吉四代"
        assert imported[0].original_price == 12800
        assert imported[1].category == "注射类"

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    print("✅")


def test_pdf():
    print("🔧 测试PDF生成...", end=" ")
    test_dir = tempfile.mkdtemp()
    try:
        from app.core.pdf_generator import PDFGenerator

        items = [
            PriceItem(name="热玛吉四代 900发", category="光电类",
                     original_price=12800, member_price=9800, remark="面部"),
            PriceItem(name="乔雅登雅致", category="注射类",
                     original_price=6800, member_price=5800, remark="0.8ml"),
            PriceItem(name="小气泡清洁", category="清洁补水",
                     original_price=298, member_price=99, remark="首次体验"),
        ]

        pdf_path = os.path.join(test_dir, "test.pdf")
        result = PDFGenerator.generate_a4_price_list(items, pdf_path)
        assert os.path.exists(result), "PDF未生成"
        assert os.path.getsize(result) > 1000

        consultant_path = os.path.join(test_dir, "consultant.pdf")
        result2 = PDFGenerator.generate_consultant_list(items, consultant_path)
        assert os.path.exists(result2), "咨询师版未生成"
        assert os.path.getsize(result2) > 1000

        csv_path = os.path.join(test_dir, "consultant.csv")
        result3 = PDFGenerator.generate_csv_consultant_list(items, csv_path)
        assert os.path.exists(result3)

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
    print("✅")


def main():
    print("=" * 50)
    print("  医美价目表工具 - 核心功能自测")
    print("=" * 50)
    print()

    tests = [
        test_models,
        test_category,
        test_price_calculator,
        test_validator,
        test_conflict_resolver,
        test_data_manager,
        test_excel,
        test_pdf,
    ]

    passed = 0
    failed = []

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ 失败: {test.__name__}")
            print(f"   错误: {e}")
            import traceback
            traceback.print_exc()
            failed.append(test.__name__)

    print()
    print("=" * 50)
    print(f"  测试结果: {passed}/{len(tests)} 通过")
    if failed:
        print(f"  失败项: {', '.join(failed)}")
        sys.exit(1)
    else:
        print("  🎉 所有核心功能测试通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
