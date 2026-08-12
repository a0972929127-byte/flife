"""
monte_carlo.py — Flife 蒙地卡羅模擬引擎（Phase 2）

在 simulate_lifetime 的固定報酬率基礎上，把「報酬率」從常數換成隨機抽樣，
重複跑 N 次，統計成功率與資產分布（P10/P50/P90 走勢帶狀圖）。

兩種抽樣模式：
- "normal"：常態分布抽樣（給定年化平均報酬與標準差）
- "historical"：從歷史年報酬率清單中逐年獨立重抽樣

historical 模式使用台灣加權股價指數（TAIEX）1996~2025年的真實年度漲跌幅
（資料來源：Wikipedia「TAIEX」條目，原始出處為台灣證交所TWSE／CEIC／
Yahoo Finance，取值為年線收盤價漲跌幅）。

這是「價格指數」報酬，不含股息——0050這類ETF的實際總報酬（含息）
長期會比這裡的數字高（台股平均股息殖利率約3~4%/年），所以這份清單
對「總報酬」而言是稍微保守的估計，不是高估。之後如果要換成真正的
含息報酬率（例如台灣加權「報酬指數」或0050還原股價報酬），
把 TAIEX_HISTORICAL_RETURNS 換成新清單即可，其餘邏輯不用動。
"""

import random
from dataclasses import dataclass
from typing import List, Optional

from core.pension_bridge_simulator import LifeEvent, simulate_lifetime

# 台灣加權股價指數（TAIEX）1996~2025 年度報酬率（不含股息）
# 來源：https://en.wikipedia.org/wiki/TAIEX （原始出處 TWSE / CEIC / Yahoo Finance）
TAIEX_HISTORICAL_RETURNS = [
       0.3441,   # 1996
       0.1808,   # 1997
       -0.2160,  # 1998
       0.3163,   # 1999
       -0.4385,  # 2000
       0.1702,   # 2001
       -0.1979,  # 2002
       0.3230,   # 2003
       0.0423,   # 2004
       0.0666,   # 2005
       0.1948,   # 2006
       0.0872,   # 2007
       -0.4603,  # 2008
       0.7834,   # 2009
       0.0958,   # 2010
       -0.2118,  # 2011
       0.0887,   # 2012
       0.1185,   # 2013
       0.0808,   # 2014
       -0.1041,  # 2015
       0.1098,   # 2016
       0.1501,   # 2017
       -0.0860,  # 2018
       0.2333,   # 2019
       0.2280,   # 2020
       0.2366,   # 2021
       -0.2240,  # 2022
       0.2683,   # 2023
       0.2847,   # 2024
       0.2574,   # 2025
]

@dataclass
class MonteCarloResult:
       n_simulations: int
       ages: List[int]
       success_rate: float
       final_balances: List[float]
       depleted_ages: List[Optional[int]]
       balance_trajectories: List[List[float]]  # [模擬編號][年份索引]

    def percentile_band(self, p: float) -> List[float]:
               """回傳每個年齡的第 p 百分位資產走勢，用來畫 fan chart。"""
               n_years = len(self.ages)
               band = []
               for year_idx in range(n_years):
                              values = sorted(traj[year_idx] for traj in self.balance_trajectories)
                              idx = min(int(len(values) * p / 100), len(values) - 1)
                              band.append(values[idx])
                          return band

    def final_percentile(self, p: float) -> float:
               values = sorted(self.final_balances)
        idx = min(int(len(values) * p / 100), len(values) - 1)
        return values[idx]

    def summary(self) -> str:
               return "\n".join([
                   f"模擬次數：{self.n_simulations}",
                   f"成功率（撐到終點）：{self.success_rate:.1%}",
                   f"最終資產 P10（悲觀情境）：{self.final_percentile(10):,.0f} 元",
                   f"最終資產中位數：{self.final_percentile(50):,.0f} 元",
                   f"最終資產 P90（樂觀情境）：{self.final_percentile(90):,.0f} 元",
    ])


def run_monte_carlo(
       n_simulations: int,
       current_age: int,
       retirement_age: int,
       death_age: int,
       current_layer1_balance: float,
       annual_savings_pre_retirement: float,
       annual_expense_today: float,
       inflation_rate: float,
       pre_retirement_return_mean: float,
       pre_retirement_return_stddev: float,
       post_retirement_return_mean: float,
       post_retirement_return_stddev: float,
       return_sampling_mode: str = "normal",  # "normal" or "historical"
       historical_returns_pool: Optional[List[float]] = None,
       pension_unlock_age: int = 60,
       labor_pension_lump_sum: float = 0.0,
       labor_pension_take_as: str = "lump_sum",
       labor_pension_monthly: float = 0.0,
       labor_insurance_claim_age: int = 60,
       labor_insurance_monthly: float = 0.0,
       life_events: Optional[List[LifeEvent]] = None,
       seed: Optional[int] = None,
) -> MonteCarloResult:
       """
           重複跑 simulate_lifetime N 次，每次每一年獨立抽樣報酬率
               （逐年獨立抽樣，非序列相關；之後要做「連續熊市」這種序列風險測試，
                   可以在 historical 模式改成 block bootstrap，抽連續區塊而非單年）。
                       """
    if seed is not None:
               random.seed(seed)

    historical_pool = historical_returns_pool or TAIEX_HISTORICAL_RETURNS
    ages = list(range(current_age, death_age + 1))

    successes = 0
    final_balances = []
    depleted_ages = []
    trajectories = []

    for _ in range(n_simulations):
               sampled_returns = {}
        for age in ages:
                       phase = "accumulation" if age < retirement_age else "drawdown"
                       if return_sampling_mode == "normal":
                                          mean = pre_retirement_return_mean if phase == "accumulation" else post_retirement_return_mean
                                          stddev = (
                                              pre_retirement_return_stddev
                                              if phase == "accumulation"
                                              else post_retirement_return_stddev
                                          )
                                          sampled_returns[age] = random.gauss(mean, stddev)
elif return_sampling_mode == "historical":
                sampled_returns[age] = random.choice(historical_pool)
else:
                raise ValueError(f"未知的抽樣模式: {return_sampling_mode}")

        result = simulate_lifetime(
                       current_age=current_age,
                       retirement_age=retirement_age,
                       death_age=death_age,
                       current_layer1_balance=current_layer1_balance,
                       annual_savings_pre_retirement=annual_savings_pre_retirement,
                       annual_expense_today=annual_expense_today,
                       inflation_rate=inflation_rate,
                       pre_retirement_return=pre_retirement_return_mean,
                       post_retirement_return=post_retirement_return_mean,
                       pension_unlock_age=pension_unlock_age,
                       labor_pension_lump_sum=labor_pension_lump_sum,
                       labor_pension_take_as=labor_pension_take_as,
                       labor_pension_monthly=labor_pension_monthly,
                       labor_insurance_claim_age=labor_insurance_claim_age,
                       labor_insurance_monthly=labor_insurance_monthly,
                       life_events=life_events,
                       return_rate_override=lambda age, phase, _sampled=sampled_returns: _sampled[age],
        )

        if result.success:
                       successes += 1
                   trajectory = [r.balance_end for r in result.records]
        trajectories.append(trajectory)
        final_balances.append(trajectory[-1])
        depleted_ages.append(result.depleted_at_age)

    return MonteCarloResult(
               n_simulations=n_simulations,
               ages=ages,
               success_rate=successes / n_simulations,
               final_balances=final_balances,
               depleted_ages=depleted_ages,
               balance_trajectories=trajectories,
    )


if __name__ == "__main__":
       import time

    t0 = time.time()
    mc = run_monte_carlo(
               n_simulations=500,
               current_age=30,
               retirement_age=50,
               death_age=90,
               current_layer1_balance=2_247_182,
               annual_savings_pre_retirement=780_000,
               annual_expense_today=492_000,
               inflation_rate=0.02,
               pre_retirement_return_mean=0.06,
               pre_retirement_return_stddev=0.15,
               post_retirement_return_mean=0.045,
               post_retirement_return_stddev=0.10,
               return_sampling_mode="normal",
               labor_pension_lump_sum=5_332_248,
               labor_insurance_monthly=14_198,
               life_events=[
                              LifeEvent(age=31, label="旅遊基金(第1年)", amount=-100_000),
                              LifeEvent(age=32, label="旅遊基金(第2年)", amount=-100_000),
                              LifeEvent(age=33, label="旅遊基金(第3年)", amount=-100_000),
                              LifeEvent(age=45, label="買房自備款(示範金額)", amount=-3_000_000),
               ],
               seed=42,
    )
    elapsed = time.time() - t0

    print(mc.summary())
    print(f"\n耗時：{elapsed:.2f} 秒（500次模擬）")
