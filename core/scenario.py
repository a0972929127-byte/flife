"""
scenario.py — Flife 情境比較模組（Phase 3）

把一組完整的輸入參數包成一個「情境」（Scenario），方便同時模擬多組情境並排比較
（例如「50歲退休」vs「55歲退休」，或「有買房」vs「沒買房」）。

跟蒙地卡羅一樣，這裡不重寫模擬邏輯，只是把參數包起來、重複呼叫 simulate_lifetime。
"""

from dataclasses import dataclass, field
from typing import Dict, List

from core.pension_bridge_simulator import LifeEvent, SimulationResult, simulate_lifetime


@dataclass
class Scenario:
    name: str
    current_age: int
    retirement_age: int
    death_age: int
    current_layer1_balance: float
    annual_savings_pre_retirement: float
    annual_expense_today: float
    inflation_rate: float
    pre_retirement_return: float
    post_retirement_return: float
    pension_unlock_age: int = 60
    labor_pension_lump_sum: float = 0.0
    labor_pension_take_as: str = "lump_sum"
    labor_pension_monthly: float = 0.0
    labor_insurance_claim_age: int = 60
    labor_insurance_monthly: float = 0.0
    life_events: List[LifeEvent] = field(default_factory=list)

    def run(self) -> SimulationResult:
        return simulate_lifetime(
            current_age=self.current_age,
            retirement_age=self.retirement_age,
            death_age=self.death_age,
            current_layer1_balance=self.current_layer1_balance,
            annual_savings_pre_retirement=self.annual_savings_pre_retirement,
            annual_expense_today=self.annual_expense_today,
            inflation_rate=self.inflation_rate,
            pre_retirement_return=self.pre_retirement_return,
            post_retirement_return=self.post_retirement_return,
            pension_unlock_age=self.pension_unlock_age,
            labor_pension_lump_sum=self.labor_pension_lump_sum,
            labor_pension_take_as=self.labor_pension_take_as,
            labor_pension_monthly=self.labor_pension_monthly,
            labor_insurance_claim_age=self.labor_insurance_claim_age,
            labor_insurance_monthly=self.labor_insurance_monthly,
            life_events=self.life_events,
        )


def compare_scenarios(scenarios: List[Scenario]) -> Dict[str, SimulationResult]:
    """跑一組情境清單，回傳 {情境名稱: 模擬結果}。"""
    return {s.name: s.run() for s in scenarios}
