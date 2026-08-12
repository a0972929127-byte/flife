"""
pension_bridge_simulator.py — Flife 核心運算模組

台灣退休金「三層資產」＋「人生事件」完整時間軸模擬引擎。

三層資產：
- Layer 1（自由資產）：隨時可動用
- Layer 2（勞退新制個人專戶）：60歲解鎖，可選一次領或月退
- Layer 3（勞保老年給付）：60歲減額請領 / 65歲全額，終身年金

時間軸分兩階段，但同一個迴圈處理：
- 累積期（現在 → 退休年齡）：還在工作，每年淨儲蓄流入
- 提領期（退休年齡 → 終點）：沒有工作收入，靠資產＋勞退＋勞保支應年支出

人生事件（LifeEvent）是資料驅動設計：買房頭期款、旅遊基金、轉職降薪…
這些都用同一組資料結構描述，不需要修改核心邏輯，UI 層可以自由新增/刪除。

固定報酬率版本（MVP）；之後把 return 參數換成隨機抽樣即可升級成蒙地卡羅。
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class LifeEvent:
    """
    一筆人生事件（買房、旅遊、轉職降薪…）。

    age: 事件發生（或開始）的年齡
    label: 顯示用名稱
    amount: 現金流，支出為負、收入為正
    recurring: 是否每年重複（例如「轉自由業後年收降低」）
    end_age: 只有 recurring=True 時有意義；None 代表持續到模擬終點
    """
    age: int
    label: str
    amount: float
    recurring: bool = False
    end_age: Optional[int] = None


@dataclass
class YearRecord:
    age: int
    phase: str  # "accumulation"（累積期）or "drawdown"（提領期）
    balance_start: float
    investment_growth: float
    savings_or_expense: float  # 累積期為正（儲蓄），提領期為負（支出）
    labor_pension_inflow: float
    labor_insurance_inflow: float
    life_event_flow: float
    life_event_labels: str
    balance_end: float


@dataclass
class SimulationResult:
    records: List[YearRecord] = field(default_factory=list)
    success: bool = True
    depleted_at_age: Optional[int] = None

    def summary(self) -> str:
        lines = []
        lines.append(
            f"{'年齡':>4} {'階段':>6} {'期初餘額':>13} {'投資成長':>11} {'儲蓄/支出':>12} "
            f"{'勞退':>10} {'勞保':>10} {'事件':>12} {'期末餘額':>13}"
        )
        for r in self.records:
            phase_label = "累積" if r.phase == "accumulation" else "提領"
            lines.append(
                f"{r.age:>4} {phase_label:>6} {r.balance_start:>13,.0f} {r.investment_growth:>11,.0f} "
                f"{r.savings_or_expense:>12,.0f} {r.labor_pension_inflow:>10,.0f} "
                f"{r.labor_insurance_inflow:>10,.0f} {r.life_event_flow:>12,.0f} {r.balance_end:>13,.0f}"
            )
        status = "✅ 資產撐到終點" if self.success else f"❌ 於 {self.depleted_at_age} 歲歸零"
        lines.append(f"\n{status}")

        event_log = [
            f"  {r.age}歲：{r.life_event_labels}（{r.life_event_flow:,.0f} 元）"
            for r in self.records if r.life_event_labels
        ]
        if event_log:
            lines.append("\n人生事件紀錄：")
            lines.extend(event_log)

        return "\n".join(lines)


def project_labor_pension_account(
    current_balance: float,
    years_to_unlock: int,
    monthly_contribution_base: float,
    contribution_rate: float,
    annual_return: float,
) -> float:
    """
    推算 60 歲時勞退新制個人專戶的累積金額。
    以「目前實際餘額」（建議從勞保局e化服務查詢）為起點，往後推算，
    不重建過去的歷史提繳紀錄。
    """
    annual_contribution = monthly_contribution_base * 12 * contribution_rate

    fv_existing = current_balance * (1 + annual_return) ** years_to_unlock

    if annual_return == 0:
        fv_contributions = annual_contribution * years_to_unlock
    else:
        fv_contributions = annual_contribution * (
            ((1 + annual_return) ** years_to_unlock - 1) / annual_return
        )

    return fv_existing + fv_contributions


def calc_labor_insurance_monthly_pension(
    avg_monthly_insured_salary: float,
    years_of_service: float,
    claim_age: int,
) -> float:
    """
    計算勞保老年年金月給付金額（A式/B式取高，並套用提前減額）。
    claim_age: 60~64 每提前一年減4%（最多提前5年，減20%）；65歲為全額。
    """
    if claim_age < 60:
        raise ValueError("勞保老年年金最早60歲才能請領")

    formula_a = avg_monthly_insured_salary * years_of_service * 0.00775 + 3000
    formula_b = avg_monthly_insured_salary * years_of_service * 0.0155
    base_monthly = max(formula_a, formula_b)

    years_early = min(max(0, 65 - claim_age), 5)
    reduction = years_early * 0.04

    return base_monthly * (1 - reduction)


def _life_event_flow_for_age(life_events: List[LifeEvent], age: int, death_age: int):
    """回傳某一年所有人生事件的合計現金流，以及觸發的事件名稱清單。"""
    total = 0.0
    labels = []
    for ev in life_events:
        if ev.recurring:
            end = ev.end_age if ev.end_age is not None else death_age
            if ev.age <= age <= end:
                total += ev.amount
                labels.append(ev.label)
        else:
            if age == ev.age:
                total += ev.amount
                labels.append(ev.label)
    return total, "、".join(labels)


def simulate_lifetime(
    current_age: int,
    retirement_age: int,
    death_age: int,
    current_layer1_balance: float,
    annual_savings_pre_retirement: float,
    annual_expense_today: float,
    inflation_rate: float,
    pre_retirement_return: float,
    post_retirement_return: float,
    pension_unlock_age: int = 60,
    labor_pension_lump_sum: float = 0.0,
    labor_pension_take_as: str = "lump_sum",  # "lump_sum" or "monthly"
    labor_pension_monthly: float = 0.0,
    labor_insurance_claim_age: int = 60,
    labor_insurance_monthly: float = 0.0,
    life_events: Optional[List[LifeEvent]] = None,
    return_rate_override: Optional[Callable[[int, str], float]] = None,
) -> SimulationResult:
    """
    從「現在」逐年模擬到「終點」，涵蓋累積期＋提領期，並疊加人生事件。

    return_rate_override: 若提供，優先於 pre/post_retirement_return 使用，
    簽名為 (age, phase) -> 報酬率。蒙地卡羅模擬靠這個接口注入隨機報酬率，
    不需要重寫這裡的迴圈邏輯。

    - 累積期（current_age → retirement_age）：資產成長 + 每年淨儲蓄流入
    - 提領期（retirement_age → death_age）：資產成長 - 年支出（隨通膨調整）
    - 60歲（或設定的解鎖年齡）：勞退挹注（一次領或轉月退）
    - labor_insurance_claim_age 起：勞保月退終身挹注
    - life_events：任何年齡都可能觸發，不分累積期/提領期
    """
    result = SimulationResult()
    life_events = life_events or []

    balance = current_layer1_balance
    expense_this_year = annual_expense_today
    lump_sum_added = False

    for age in range(current_age, death_age + 1):
        start_balance = balance
        phase = "accumulation" if age < retirement_age else "drawdown"
        if return_rate_override is not None:
            return_rate = return_rate_override(age, phase)
        else:
            return_rate = pre_retirement_return if phase == "accumulation" else post_retirement_return

        growth = balance * return_rate
        balance += growth

        if phase == "accumulation":
            savings_or_expense = annual_savings_pre_retirement
        else:
            savings_or_expense = -expense_this_year
        balance += savings_or_expense

        pension_inflow = 0.0
        insurance_inflow = 0.0

        if age == pension_unlock_age and labor_pension_take_as == "lump_sum" and not lump_sum_added:
            pension_inflow += labor_pension_lump_sum
            lump_sum_added = True

        if labor_pension_take_as == "monthly" and age >= pension_unlock_age:
            pension_inflow += labor_pension_monthly * 12

        if age >= labor_insurance_claim_age:
            insurance_inflow += labor_insurance_monthly * 12

        balance += pension_inflow + insurance_inflow

        event_flow, event_labels = _life_event_flow_for_age(life_events, age, death_age)
        balance += event_flow

        result.records.append(
            YearRecord(
                age=age,
                phase=phase,
                balance_start=start_balance,
                investment_growth=growth,
                savings_or_expense=savings_or_expense,
                labor_pension_inflow=pension_inflow,
                labor_insurance_inflow=insurance_inflow,
                life_event_flow=event_flow,
                life_event_labels=event_labels,
                balance_end=balance,
            )
        )

        if balance < 0 and result.success:
            result.success = False
            result.depleted_at_age = age

        # 通膨每年累積（不論累積期或提領期都往前滾，確保退休當年的支出已反映通膨）
        expense_this_year *= (1 + inflation_rate)

    return result


if __name__ == "__main__":
    # ------------------------------------------------------------------
    # 示範：帶入你之前提供的真實數字（存款、月支出），其餘（勞退/勞保細節、
    # 退休前年儲蓄）目前還是假設值，等你查到真實資料後再替換。
    # ------------------------------------------------------------------

    labor_pension_at_60 = project_labor_pension_account(
        current_balance=150_000,           # 假設值：目前勞退個人專戶餘額
        years_to_unlock=30,                # 30歲 → 60歲
        monthly_contribution_base=60_000,  # 假設值：月提繳工資
        contribution_rate=0.12,
        annual_return=0.04,
    )

    labor_insurance_monthly = calc_labor_insurance_monthly_pension(
        avg_monthly_insured_salary=45_800,  # 假設值
        years_of_service=25,                # 假設值
        claim_age=60,
    )

    life_events = [
        LifeEvent(age=31, label="旅遊基金(第1年)", amount=-100_000),
        LifeEvent(age=32, label="旅遊基金(第2年)", amount=-100_000),
        LifeEvent(age=33, label="旅遊基金(第3年)", amount=-100_000),
        LifeEvent(age=45, label="買房自備款(示範金額，未來可調整年齡/金額)", amount=-3_000_000),
    ]

    sim = simulate_lifetime(
        current_age=30,
        retirement_age=50,
        death_age=90,
        current_layer1_balance=2_247_182,      # 你提供的目前總存款（含股票+配息）
        annual_savings_pre_retirement=780_000, # 假設值：估算的年儲蓄能力，待你確認
        annual_expense_today=492_000,          # 你提供的月開銷4.1萬 × 12
        inflation_rate=0.02,
        pre_retirement_return=0.06,
        post_retirement_return=0.045,
        pension_unlock_age=60,
        labor_pension_lump_sum=labor_pension_at_60,
        labor_pension_take_as="lump_sum",
        labor_insurance_claim_age=60,
        labor_insurance_monthly=labor_insurance_monthly,
        life_events=life_events,
    )

    print(f"60歲時勞退個人專戶估計累積：{labor_pension_at_60:,.0f} 元")
    print(f"勞保老年年金月給付（60歲提前請領）：{labor_insurance_monthly:,.0f} 元/月\n")
    print(sim.summary())
