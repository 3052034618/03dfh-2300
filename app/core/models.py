from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime


@dataclass
class PriceItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    display_name: str = ""
    internal_name: str = ""
    category: str = ""
    original_price: float = 0.0
    member_price: float = 0.0
    doctor_fee: float = 0.0
    material_fee: float = 0.0
    material_brand: str = ""
    cost_price: float = 0.0
    remark: str = ""
    is_conflict: bool = False
    conflict_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total_cost(self) -> float:
        return round(self.doctor_fee + self.material_fee + self.cost_price, 2)

    @property
    def member_profit(self) -> float:
        return round(self.member_price - self.total_cost, 2)

    @property
    def original_profit(self) -> float:
        return round(self.original_price - self.total_cost, 2)

    def validate(self) -> List[str]:
        errors = []
        if not self.name:
            errors.append("项目名称不能为空")
        if self.original_price < 0:
            errors.append(f"项目[{self.name}]原价不能为负数")
        if self.member_price < 0:
            errors.append(f"项目[{self.name}]会员价不能为负数")
        if self.member_price > self.original_price and self.original_price > 0:
            errors.append(f"项目[{self.name}]会员价({self.member_price})高于原价({self.original_price})")
        if self.original_price > 0 and self.original_price < self.total_cost:
            errors.append(f"项目[{self.name}]原价({self.original_price})低于成本价({self.total_cost})")
        if self.member_price > 0 and self.member_price < self.total_cost:
            errors.append(f"项目[{self.name}]会员价({self.member_price})低于成本价({self.total_cost})")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["total_cost"] = self.total_cost
        data["member_profit"] = self.member_profit
        data["original_profit"] = self.original_profit
        return data

    def update_timestamp(self):
        self.updated_at = datetime.now().isoformat()


@dataclass
class Snapshot:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    item_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CategoryManager:
    CATEGORIES = {
        "光电类": ["光电", "激光", "光子", "射频", "超声", "热玛吉", "欧洲之星", "皮秒", "超皮秒", "点阵"],
        "注射类": ["注射", "玻尿酸", "肉毒素", "瘦脸", "除皱", "填充", "水光", "溶脂"],
        "手术类": ["手术", "双眼皮", "隆鼻", "吸脂", "隆胸", "拉皮", "眼袋", "自体脂肪"],
        "清洁补水": ["清洁", "补水", "小气泡", "水氧", "导入", "面膜", "焕肤", "果酸", "水杨酸"],
        "皮肤护理": ["护理", "SPA", "按摩", "养生", "身体", "脱毛", "纹绣", "半永久"],
        "其他": []
    }

    @classmethod
    def detect_category(cls, name: str) -> str:
        if not name:
            return "其他"
        for category, keywords in cls.CATEGORIES.items():
            for keyword in keywords:
                if keyword in name:
                    return category
        return "其他"

    @classmethod
    def get_all_categories(cls) -> List[str]:
        return list(cls.CATEGORIES.keys())
