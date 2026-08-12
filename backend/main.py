"""
main.py — Flife FastAPI 後端（多人匿名版）

不需要登入：所有請求都帶著前端產生的匿名 device_id，
後端只用它區隔「這是誰的資料」，不做任何帳號密碼驗證。

執行方式：
    cd backend
    uvicorn main:app --reload
"""

import sys
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent.parent))

import db  # noqa: E402  (同資料夾內的模組，需先設定sys.path後再import跨層的core)
from core.monte_carlo import run_monte_carlo  # noqa: E402
from core.pension_bridge_simulator import (  # noqa: E402
    LifeEvent,
    calc_labor_insurance_monthly_pension,
    project_labor_pension_account,
    simulate_lifetime,
)
from core.scenario import Scenario, compare_scenarios  # noqa: E402

app = FastAPI(title="Flife API")

# 開發階段先開放全部來源；之後前端網域確定了，建議改成白名單
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


# 也在模組載入時直接初始化一次：確保用 TestClient 或不觸發 lifespan 事件的
# 執行方式（例如某些測試工具）時，資料表還是會被建立。
db.init_db()


# ----------------------------------------------------------------------
# 共用的輸入模型
# ----------------------------------------------------------------------
class LifeEventIn(BaseModel):
    age: int
    label: str
    amount: float
    recurring: bool = False
    end_age: Optional[int] = None


class SimulateParams(BaseModel):
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
    labor_pension_take_as: Literal["lump_sum", "monthly"] = "lump_sum"
    labor_pension_monthly: float = 0.0
    labor_insurance_claim_age: int = 60
    labor_insurance_monthly: float = 0.0
    life_events: List[LifeEventIn] = []


def _to_life_events(items: List[LifeEventIn]) -> List[LifeEvent]:
    return [LifeEvent(**item.model_dump()) for item in items]


# ----------------------------------------------------------------------
# 核心試算 API
# ----------------------------------------------------------------------
@app.post("/api/simulate")
def simulate(params: SimulateParams):
    result = simulate_lifetime(
        current_age=params.current_age,
        retirement_age=params.retirement_age,
        death_age=params.death_age,
        current_layer1_balance=params.current_layer1_balance,
        annual_savings_pre_retirement=params.annual_savings_pre_retirement,
        annual_expense_today=params.annual_expense_today,
        inflation_rate=params.inflation_rate,
        pre_retirement_return=params.pre_retirement_return,
        post_retirement_return=params.post_retirement_return,
        pension_unlock_age=params.pension_unlock_age,
        labor_pension_lump_sum=params.labor_pension_lump_sum,
        labor_pension_take_as=params.labor_pension_take_as,
        labor_pension_monthly=params.labor_pension_monthly,
        labor_insurance_claim_age=params.labor_insurance_claim_age,
        labor_insurance_monthly=params.labor_insurance_monthly,
        life_events=_to_life_events(params.life_events),
    )
    return {
        "success": result.success,
        "depleted_at_age": result.depleted_at_age,
        "records": [
            {
                "age": r.age,
                "phase": r.phase,
                "balance_start": r.balance_start,
                "investment_growth": r.investment_growth,
                "savings_or_expense": r.savings_or_expense,
                "labor_pension_inflow": r.labor_pension_inflow,
                "labor_insurance_inflow": r.labor_insurance_inflow,
                "life_event_flow": r.life_event_flow,
                "life_event_labels": r.life_event_labels,
                "balance_end": r.balance_end,
            }
            for r in result.records
        ],
    }


class MonteCarloParams(SimulateParams):
    n_simulations: int = 1000
    pre_retirement_return_stddev: float = 0.15
    post_retirement_return_stddev: float = 0.10
    return_sampling_mode: Literal["normal", "historical"] = "normal"
    seed: Optional[int] = None


@app.post("/api/monte-carlo")
def monte_carlo(params: MonteCarloParams):
    mc = run_monte_carlo(
        n_simulations=params.n_simulations,
        current_age=params.current_age,
        retirement_age=params.retirement_age,
        death_age=params.death_age,
        current_layer1_balance=params.current_layer1_balance,
        annual_savings_pre_retirement=params.annual_savings_pre_retirement,
        annual_expense_today=params.annual_expense_today,
        inflation_rate=params.inflation_rate,
        pre_retirement_return_mean=params.pre_retirement_return,
        pre_retirement_return_stddev=params.pre_retirement_return_stddev,
        post_retirement_return_mean=params.post_retirement_return,
        post_retirement_return_stddev=params.post_retirement_return_stddev,
        return_sampling_mode=params.return_sampling_mode,
        pension_unlock_age=params.pension_unlock_age,
        labor_pension_lump_sum=params.labor_pension_lump_sum,
        labor_pension_take_as=params.labor_pension_take_as,
        labor_pension_monthly=params.labor_pension_monthly,
        labor_insurance_claim_age=params.labor_insurance_claim_age,
        labor_insurance_monthly=params.labor_insurance_monthly,
        life_events=_to_life_events(params.life_events),
        seed=params.seed,
    )
    return {
        "success_rate": mc.success_rate,
        "n_simulations": mc.n_simulations,
        "ages": mc.ages,
        "p10_band": mc.percentile_band(10),
        "p50_band": mc.percentile_band(50),
        "p90_band": mc.percentile_band(90),
        "final_p10": mc.final_percentile(10),
        "final_p50": mc.final_percentile(50),
        "final_p90": mc.final_percentile(90),
    }


class LaborPensionParams(BaseModel):
    current_balance: float
    years_to_unlock: int
    monthly_contribution_base: float
    contribution_rate: float = 0.12
    annual_return: float = 0.04


@app.post("/api/labor-pension-projection")
def labor_pension_projection(params: LaborPensionParams):
    value = project_labor_pension_account(**params.model_dump())
    return {"projected_balance_at_unlock": value}


class LaborInsuranceParams(BaseModel):
    avg_monthly_insured_salary: float
    years_of_service: float
    claim_age: int = 60


@app.post("/api/labor-insurance-pension")
def labor_insurance_pension(params: LaborInsuranceParams):
    value = calc_labor_insurance_monthly_pension(**params.model_dump())
    return {"monthly_pension": value}


# ----------------------------------------------------------------------
# 匿名情境儲存 API
# ----------------------------------------------------------------------
class SaveScenarioRequest(BaseModel):
    device_id: str
    name: str
    params: SimulateParams


@app.post("/api/scenarios")
def save_scenario(req: SaveScenarioRequest):
    scenario_id = db.save_scenario(req.device_id, req.name, req.params.model_dump())
    return {"id": scenario_id}


@app.get("/api/scenarios")
def list_scenarios(device_id: str):
    return db.list_scenarios(device_id)


@app.delete("/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str, device_id: str):
    ok = db.delete_scenario(scenario_id, device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="找不到這個情境，或不屬於你的裝置")
    return {"deleted": True}


class CompareRequest(BaseModel):
    device_id: str
    scenario_ids: List[str]


@app.post("/api/scenarios/compare")
def compare(req: CompareRequest):
    scenarios = []
    for sid in req.scenario_ids:
        record = db.get_scenario(sid, req.device_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"找不到情境 {sid}")
        p = record["params"]
        scenarios.append(
            Scenario(
                name=record["name"],
                current_age=p["current_age"],
                retirement_age=p["retirement_age"],
                death_age=p["death_age"],
                current_layer1_balance=p["current_layer1_balance"],
                annual_savings_pre_retirement=p["annual_savings_pre_retirement"],
                annual_expense_today=p["annual_expense_today"],
                inflation_rate=p["inflation_rate"],
                pre_retirement_return=p["pre_retirement_return"],
                post_retirement_return=p["post_retirement_return"],
                pension_unlock_age=p.get("pension_unlock_age", 60),
                labor_pension_lump_sum=p.get("labor_pension_lump_sum", 0.0),
                labor_pension_take_as=p.get("labor_pension_take_as", "lump_sum"),
                labor_pension_monthly=p.get("labor_pension_monthly", 0.0),
                labor_insurance_claim_age=p.get("labor_insurance_claim_age", 60),
                labor_insurance_monthly=p.get("labor_insurance_monthly", 0.0),
                life_events=[LifeEvent(**e) for e in p.get("life_events", [])],
            )
        )
    results = compare_scenarios(scenarios)
    return {
        name: {
            "success": res.success,
            "depleted_at_age": res.depleted_at_age,
            "final_balance": res.records[-1].balance_end,
            "ages": [r.age for r in res.records],
            "balances": [r.balance_end for r in res.records],
        }
        for name, res in results.items()
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ----------------------------------------------------------------------
# 把前端（純靜態HTML/CSS/JS，無build流程）一起服務出去，
# 這樣部署只需要一個網址，不用另外託管前端。
# 必須放在所有 /api/... 路由之後，這樣API路徑才會優先匹配，
# 其餘路徑（例如 / 、/index.html）才會落到這裡由靜態檔案處理。
# ----------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
