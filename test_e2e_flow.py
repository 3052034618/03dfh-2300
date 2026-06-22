"""端到端流程测试：低于成本价导入 -> 校验 -> 修复 -> 保存 -> 重启验证"""

import os
import sys
import shutil
import tempfile
from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.models import PriceItem
from app.core.data_manager import ExcelImporter, DataStore
from app.core.price_engine import PriceValidator


def make_test_excel(file_path: str):
    """生成包含低于成本价项目的测试 Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "价目表"
    ws.append([
        "项目名称", "分类", "原价", "会员价",
        "医生费", "耗材费", "成本价", "备注"
    ])
    ws.append([
        "热玛吉第五代面部", "光电类",
        800.00,   # 原价（故意低于成本）
        680.00,   # 会员价（也低于成本）
        1500.00,  # 医生费
        800.00,   # 耗材费
        200.00,   # 成本价
        "总成本 = 1500+800+200 = 2500，原价800远低于成本"
    ])
    ws.append([
        "乔雅登极致玻尿酸", "注射类",
        3000.00,  # 原价（正常）
        1200.00,  # 会员价（低于成本）
        600.00,   # 医生费
        1500.00,  # 耗材费
        300.00,   # 成本价
        "总成本 = 600+1500+300 = 2400，会员价1200低于成本"
    ])
    ws.append([
        "光子嫩肤全模式", "光电类",
        1500.00,  # 原价
        1200.00,  # 会员价
        200.00,   # 医生费
        100.00,   # 耗材费
        50.00,    # 成本价
        "总成本 = 350，全部正常，用于对比"
    ])
    wb.save(file_path)
    print(f"[OK] 测试Excel已生成: {file_path}")


def simulate_fix_cost_prices(items):
    """模拟 validation_page._fix_cost_prices 的修复逻辑"""
    below_items = PriceValidator.check_below_cost(items)
    if not below_items:
        print("[INFO] 没有需要修复的成本价问题")
        return

    unique_items = {}
    for item, msg in below_items:
        unique_items[item.id] = item

    count = 0
    for item in unique_items.values():
        total_cost = item.total_cost
        if total_cost <= 0:
            continue
        changed = False
        if item.original_price < total_cost:
            item.original_price = round(total_cost * 1.1, 2)
            changed = True
        if item.member_price > 0 and item.member_price < total_cost:
            item.member_price = round(total_cost * 1.05, 2)
            changed = True
        if item.member_price > 0 and item.member_price >= item.original_price:
            item.member_price = round(item.original_price * 0.9, 2)
            changed = True
        if changed:
            item.update_timestamp()
            count += 1
    print(f"[OK] 已修复 {count} 个低于成本价的项目")


def test_step_1_import_with_below_cost(tmp_dir):
    """步骤1：导入含低于成本价的 Excel -> 只进内存不写盘"""
    print("\n" + "=" * 60)
    print("步骤1：导入含低于成本价的 Excel")
    print("=" * 60)

    excel_path = os.path.join(tmp_dir, "test_input.xlsx")
    make_test_excel(excel_path)

    data_dir = os.path.join(tmp_dir, "data")
    backup_dir = os.path.join(tmp_dir, "backups")
    store = DataStore(data_dir, backup_dir)

    items, warnings = ExcelImporter.import_file(excel_path)
    print(f"[INFO] 导入成功: {len(items)} 个项目, warnings={warnings}")
    assert len(items) == 3, f"应导入3个项目，实际{len(items)}"

    # --- 低于成本价检查 ---
    can_save, errors = PriceValidator.can_save(items)
    print(f"[CHECK] can_save={can_save}, 错误数={len(errors)}")
    for e in errors:
        print(f"         - {e}")
    assert can_save is False, "存在低于成本价项目时 can_save 必须返回 False"
    assert len(errors) >= 3, "至少应有3个错误(热玛吉原价+会员价+乔雅登会员价)"

    # --- 加载到内存，但不调用 save() ---
    store.set_items(items)
    print(f"[INFO] items 已加载到 store.items (set_items)，未调用 save")

    # --- 验证：current_items.json 不应有更新或仍为空 ---
    data_file = os.path.join(data_dir, "current_items.json")
    if os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"[CHECK] current_items.json 内容长度={len(content)}")
        # 如果文件存在，内容应该是空数组（初始状态）
        if content and content != "[]":
            assert False, "未调用 save() 之前 current_items.json 不应写入导入数据"
    print("[PASS] 步骤1通过：导入仅内存，未写盘")
    return store


def test_step_2_fix_and_save(store, tmp_dir):
    """步骤2：一键修复成本价 -> 保存 -> 验证持久化"""
    print("\n" + "=" * 60)
    print("步骤2：一键修复成本价 + 保存")
    print("=" * 60)

    # 修复前快照
    before_original = [it.original_price for it in store.items]
    before_member = [it.member_price for it in store.items]
    print(f"[INFO] 修复前 原价列表: {before_original}")
    print(f"[INFO] 修复前 会员价: {before_member}")

    # --- 一键修复 ---
    simulate_fix_cost_prices(store.items)
    after_original = [it.original_price for it in store.items]
    after_member = [it.member_price for it in store.items]
    print(f"[INFO] 修复后 原价列表: {after_original}")
    print(f"[INFO] 修复后 会员价: {after_member}")

    # 修复后数值断言：热玛吉总成本=2500
    thermage = next(it for it in store.items if "热玛吉" in it.name)
    assert thermage.original_price >= 2500 * 1.1, \
        f"热玛吉原价修复后应>=2750，实际={thermage.original_price}"
    assert thermage.member_price >= 2500 * 1.05, \
        f"热玛吉会员价修复后应>=2625，实际={thermage.member_price}"
    assert thermage.member_price < thermage.original_price, \
        f"会员价应低于原价: {thermage.member_price} vs {thermage.original_price}"

    # 乔雅登总成本=2400
    juvederm = next(it for it in store.items if "乔雅登" in it.name)
    assert juvederm.member_price >= 2400 * 1.05, \
        f"乔雅登会员价修复后应>=2520，实际={juvederm.member_price}"
    assert juvederm.member_price < juvederm.original_price, \
        f"乔雅登会员价修复后应仍低于原价"

    # --- 再次校验：现在应该能保存了 ---
    can_save, errors = PriceValidator.can_save(store.items)
    print(f"[CHECK] 修复后 can_save={can_save}, errors={errors}")
    assert can_save is True, f"修复后应可保存，仍有错误: {errors}"

    # --- 保存持久化 ---
    success, save_errors = store.save(
        create_snapshot=True,
        snapshot_name="测试修复后保存",
        snapshot_desc="端到端测试"
    )
    print(f"[CHECK] save() 结果: success={success}, errors={save_errors}")
    assert success is True, "保存应该成功"

    # 验证磁盘文件存在且非空
    data_file = os.path.join(store.data_dir, "current_items.json")
    assert os.path.exists(data_file), "current_items.json 应该存在"
    with open(data_file, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"[CHECK] current_items.json 写入成功，长度={len(content)}")
    assert "热玛吉" in content and "乔雅登" in content, "JSON中应包含修复后的项目名"

    # 验证快照被创建
    snaps = store.backup_manager.list_snapshots()
    print(f"[CHECK] 快照数量: {len(snaps)}")
    assert len(snaps) >= 1, "至少应有1个快照"
    print("[PASS] 步骤2通过：修复成功，持久化成功")


def test_step_3_restart_and_verify(tmp_dir):
    """步骤3：模拟重启 -> 重新实例化 DataStore -> 验证数据仍存在且正确"""
    print("\n" + "=" * 60)
    print("步骤3：模拟重启，验证数据持久化")
    print("=" * 60)

    data_dir = os.path.join(tmp_dir, "data")
    backup_dir = os.path.join(tmp_dir, "backups")

    # 重新实例化，模拟重启
    store2 = DataStore(data_dir, backup_dir)
    print(f"[INFO] 重启后加载到 {len(store2.items)} 个项目")
    assert len(store2.items) == 3, f"重启后应仍有3个项目，实际={len(store2.items)}"

    thermage = next(it for it in store2.items if "热玛吉" in it.name)
    juvederm = next(it for it in store2.items if "乔雅登" in it.name)
    photon = next(it for it in store2.items if "光子" in it.name)

    print(f"  热玛吉: 原价={thermage.original_price}, 会员={thermage.member_price}, "
          f"总成本={thermage.total_cost}")
    print(f"  乔雅登: 原价={juvederm.original_price}, 会员={juvederm.member_price}, "
          f"总成本={juvederm.total_cost}")
    print(f"  光子嫩肤: 原价={photon.original_price}, 会员={photon.member_price}, "
          f"总成本={photon.total_cost}")

    # 数值验证
    assert thermage.original_price >= 2500 * 1.1, "热玛吉原价持久化错误"
    assert thermage.member_price >= 2500 * 1.05, "热玛吉会员价持久化错误"
    assert juvederm.member_price >= 2400 * 1.05, "乔雅登会员价持久化错误"

    # 重启后保存也应该通过
    can_save, errors = PriceValidator.can_save(store2.items)
    assert can_save is True, f"重启后校验仍应通过，错误: {errors}"

    print("[PASS] 步骤3通过：重启后数据完整且正确")


def test_ui_imports():
    """测试所有 UI 模块能正常 import，不抛异常"""
    print("\n" + "=" * 60)
    print("UI 模块 Import 稳定性检查（5个页面+主窗口）")
    print("=" * 60)

    modules = [
        ("app.ui.widgets", "基础组件 widgets.py"),
        ("app.ui.import_page", "1.导入表格 import_page.py"),
        ("app.ui.validation_page", "2.价格校验 validation_page.py"),
        ("app.ui.batch_page", "3.批量调整 batch_page.py"),
        ("app.ui.print_page", "4.打印预览 print_page.py"),
        ("app.ui.backup_page", "5.备份恢复 backup_page.py"),
        ("app.ui.main_window", "主窗口 main_window.py"),
    ]

    all_ok = True
    for mod_path, desc in modules:
        try:
            __import__(mod_path)
            print(f"  [OK] {desc}")
        except Exception as e:
            print(f"  [FAIL] {desc}: {type(e).__name__}: {e}")
            all_ok = False

    if all_ok:
        print("[PASS] 全部 UI 模块 Import 成功，程序启动不会崩")
    else:
        print("[FAIL] 有 UI 模块 Import 失败，请修复")
    return all_ok


def main():
    print("医美价目管家 - 端到端流程测试")
    print("=" * 60)

    # 先做 UI import 检查（快速失败）
    ui_ok = test_ui_imports()
    if not ui_ok:
        print("\n[ABORT] UI 模块有 Import 错误，先修复再跑流程测试")
        sys.exit(1)

    # 流程测试用临时目录
    tmp_dir = tempfile.mkdtemp(prefix="medprice_e2e_")
    print(f"\n[INFO] 测试临时目录: {tmp_dir}")

    try:
        store = test_step_1_import_with_below_cost(tmp_dir)
        test_step_2_fix_and_save(store, tmp_dir)
        test_step_3_restart_and_verify(tmp_dir)

        print("\n" + "=" * 60)
        print("🎉 所有端到端测试全部通过！")
        print("=" * 60)
        print("验证总结：")
        print("  1. ✅ 低于成本价导入时只进内存，不写盘（不会误落盘）")
        print("  2. ✅ 修复后 can_save 通过，save() 正确持久化 + 创建快照")
        print("  3. ✅ 重启 DataStore 后数据和修复值完整保留")
        print("  4. ✅ 5个侧边栏页面 + 主窗口 Import 均无崩溃")

    finally:
        # 清理临时目录
        try:
            shutil.rmtree(tmp_dir)
            print(f"\n[INFO] 已清理临时目录: {tmp_dir}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
