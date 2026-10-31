from typing import List
from conditions.primitives import BaseCondition, ConditionContext

class AndCondition(BaseCondition):
    """逻辑与 (AND) 条件：所有子条件均达成时为 True"""
    def __init__(self, conditions: List[BaseCondition]):
        self.conditions = conditions

    def evaluate(self, ctx: ConditionContext) -> bool:
        if not self.conditions:
            return True
        return all(c.evaluate(ctx) for c in self.conditions)

    def get_description(self) -> str:
        if not self.conditions:
            return "TRUE"
        sub_desc = " 且 ".join([c.get_description() for c in self.conditions])
        return f"({sub_desc})"


class OrCondition(BaseCondition):
    """逻辑或 (OR) 条件：任一子条件达成时为 True"""
    def __init__(self, conditions: List[BaseCondition]):
        self.conditions = conditions

    def evaluate(self, ctx: ConditionContext) -> bool:
        if not self.conditions:
            return False
        return any(c.evaluate(ctx) for c in self.conditions)

    def get_description(self) -> str:
        if not self.conditions:
            return "FALSE"
        sub_desc = " 或 ".join([c.get_description() for c in self.conditions])
        return f"({sub_desc})"


class NotCondition(BaseCondition):
    """逻辑非 (NOT) 条件：对子条件取反"""
    def __init__(self, condition: BaseCondition):
        self.condition = condition

    def evaluate(self, ctx: ConditionContext) -> bool:
        return not self.condition.evaluate(ctx)

    def get_description(self) -> str:
        return f"非({self.condition.get_description()})"


class ConstantCondition(BaseCondition):
    """常数布尔条件"""
    def __init__(self, value: bool, description: str = ""):
        self.value = value
        self.description = description or str(value)

    def evaluate(self, ctx: ConditionContext) -> bool:
        return self.value

    def get_description(self) -> str:
        return self.description
