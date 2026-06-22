from typing import List, Tuple, Dict, Callable, Optional
from collections import defaultdict
from .models import PriceItem, CategoryManager


class PriceCalculator:
    @staticmethod
    def adjust_by_percentage(items: List[PriceItem], percentage: float,
                            filter_func: Optional[Callable[[PriceItem], bool]] = None,
                            target_fields: Optional[List[str]] = None) -> List[PriceItem]:
        if target_fields is None:
            target_fields = ["original_price", "member_price"]
        multiplier = 1 + (percentage / 100.0)
        for item in items:
            if filter_func is None or filter_func(item):
                for field_name in target_fields:
                    if hasattr(item, field_name):
                        old_value = getattr(item, field_name)
                        if old_value > 0:
                            new_value = round(old_value * multiplier, 2)
                            setattr(item, field_name, new_value)
                item.update_timestamp()
        return items

    @staticmethod
    def adjust_by_fixed_amount(items: List[PriceItem], amount: float,
                              filter_func: Optional[Callable[[PriceItem], bool]] = None,
                              target_fields: Optional[List[str]] = None) -> List[PriceItem]:
        if target_fields is None:
            target_fields = ["original_price", "member_price"]
        for item in items:
            if filter_func is None or filter_func(item):
                for field_name in target_fields:
                    if hasattr(item, field_name):
                        old_value = getattr(item, field_name)
                        if old_value > 0:
                            new_value = round(max(0, old_value + amount), 2)
                            setattr(item, field_name, new_value)
                item.update_timestamp()
        return items

    @staticmethod
    def adjust_material_fee_by_brand(items: List[PriceItem], brand: str,
                                    amount: float, is_percentage: bool = False) -> List[PriceItem]:
        for item in items:
            if brand and brand in (item.material_brand or ""):
                if is_percentage:
                    multiplier = 1 + (amount / 100.0)
                    item.material_fee = round(item.material_fee * multiplier, 2)
                else:
                    item.material_fee = round(max(0, item.material_fee + amount), 2)
                item.update_timestamp()
        return items

    @staticmethod
    def adjust_光电_items(items: List[PriceItem], percentage: float) -> List[PriceItem]:
        return PriceCalculator.adjust_by_percentage(
            items, percentage,
            filter_func=lambda x: x.category == "光电类"
        )

    @staticmethod
    def adjust_清洁补水_items(items: List[PriceItem], decrease_amount: float) -> List[PriceItem]:
        return PriceCalculator.adjust_by_fixed_amount(
            items, -abs(decrease_amount),
            filter_func=lambda x: x.category == "清洁补水"
        )


class PriceValidator:
    @staticmethod
    def check_member_above_original(items: List[PriceItem]) -> List[Tuple[PriceItem, str]]:
        issues = []
        for item in items:
            if item.original_price > 0 and item.member_price > item.original_price:
                issues.append((item, f"会员价({item.member_price})高于原价({item.original_price})"))
        return issues

    @staticmethod
    def check_below_cost(items: List[PriceItem]) -> List[Tuple[PriceItem, str]]:
        issues = []
        for item in items:
            total_cost = item.total_cost
            if item.original_price > 0 and item.original_price < total_cost:
                issues.append((item, f"原价({item.original_price})低于成本价({total_cost})"))
            if item.member_price > 0 and item.member_price < total_cost:
                issues.append((item, f"会员价({item.member_price})低于成本价({total_cost})"))
        return issues

    @staticmethod
    def check_duplicate_names(items: List[PriceItem]) -> Dict[str, List[PriceItem]]:
        name_map = defaultdict(list)
        for item in items:
            normalized_name = item.name.strip() if item.name else ""
            if normalized_name:
                name_map[normalized_name].append(item)
        return {name: group for name, group in name_map.items() if len(group) > 1}

    @staticmethod
    def check_price_conflicts_in_duplicates(duplicates: Dict[str, List[PriceItem]]) -> Dict[str, List[PriceItem]]:
        conflicts = {}
        for name, group in duplicates.items():
            prices = set()
            for item in group:
                price_key = (item.original_price, item.member_price, item.doctor_fee, item.material_fee)
                prices.add(price_key)
            if len(prices) > 1:
                conflicts[name] = group
                conflict_ids = [item.id for item in group]
                for item in group:
                    item.is_conflict = True
                    item.conflict_ids = [cid for cid in conflict_ids if cid != item.id]
        return conflicts

    @staticmethod
    def run_all_validations(items: List[PriceItem]) -> Dict[str, List]:
        member_issues = PriceValidator.check_member_above_original(items)
        cost_issues = PriceValidator.check_below_cost(items)
        duplicates = PriceValidator.check_duplicate_names(items)
        conflicts = PriceValidator.check_price_conflicts_in_duplicates(duplicates)

        return {
            "member_above_original": member_issues,
            "below_cost": cost_issues,
            "duplicate_names": duplicates,
            "price_conflicts": conflicts,
            "all_errors": [
                f"[{item.name}] {msg}" for item, msg in member_issues + cost_issues
            ]
        }

    @staticmethod
    def can_save(items: List[PriceItem]) -> Tuple[bool, List[str]]:
        errors = []
        for item in items:
            item_errors = item.validate()
            errors.extend(item_errors)
        return (len(errors) == 0, errors)


class ConflictResolver:
    @staticmethod
    def resolve_keep_highest_price(items: List[PriceItem]) -> PriceItem:
        return max(items, key=lambda x: (x.original_price, x.member_price))

    @staticmethod
    def resolve_keep_lowest_price(items: List[PriceItem]) -> PriceItem:
        return min(items, key=lambda x: (x.original_price, x.member_price))

    @staticmethod
    def resolve_keep_latest(items: List[PriceItem]) -> PriceItem:
        return max(items, key=lambda x: x.updated_at)

    @staticmethod
    def resolve_keep_first(items: List[PriceItem]) -> PriceItem:
        return items[0]

    @staticmethod
    def merge_items(base_item: PriceItem, other_items: List[PriceItem]) -> PriceItem:
        for other in other_items:
            if not base_item.display_name and other.display_name:
                base_item.display_name = other.display_name
            if not base_item.internal_name and other.internal_name:
                base_item.internal_name = other.internal_name
            if not base_item.remark and other.remark:
                base_item.remark = other.remark
            if not base_item.material_brand and other.material_brand:
                base_item.material_brand = other.material_brand
            if base_item.category == "其他" and other.category != "其他":
                base_item.category = other.category
        base_item.is_conflict = False
        base_item.conflict_ids = []
        base_item.update_timestamp()
        return base_item
