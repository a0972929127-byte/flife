"""
Flife — 台灣退休金三層資產＋人生事件 全時間軸試算工具
Phase 1: Streamlit 互動介面（固定報酬率版本）
"""

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).parent))

from core.monte_carlo import run_monte_carlo
from core.pension_bridge_simulator import (
    LifeEvent,
    calc_labor_insurance_monthly_pension,
    project_labor_pension_account,
    simulate_lifetime,
)
from core.scenario import Scenario, compare_scenarios

st.set_page_config(page_title="Flife｜退休三層資產試算", layout="wide")

st.title("Flife")
st.caption("台灣退休金三層資產試算：自由資產 × 勞退新制 × 勞保老年給付，含人生事件時間軸")

# ----------------------------------------------------------------------
# 預設人生事件（第一次開啟時的示範資料，之後可自由新增/刪除）
# ----------------------------------------------------------------------
if "life_events" not in st.session_state:
    st.session_state.life_events = [
        {"age": 31, "label": "旅遊基金(第1年)", "amount": -100_000, "recurring": False, "end_age": None},
        {"age": 32, "label": "旅遊基金(第2年)", "amount": -100_000, "recurring": False, "end_age": None},
        {"age": 33, "label": "旅遊基金(第3年)", "amount": -100_000, "recurring": False, "end_age": None},
        {"age": 45, "label": "買房自備款(示範金額)", "amount": -3_000_000, "recurring": False, "end_age": None},
    ]

# ----------------------------------------------------------------------
# 左側：輸入參數
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("基本假設")
    current_age = st.number_input("目前年齡", 18, 70, 30)
    retirement_age = st.number_input("計畫退休年齡", current_age + 1, 80, 50)
    death_age = st.number_input("試算到幾歲", retirement_age + 1, 110, 90)

    st.header("Layer 1｜自由資產")
    current_layer1_balance = st.number_input(
        "目前自由資產（元）", min_value=0, value=2_247_182, step=10_000
    )
    annual_savings_pre_retirement = st.number_input(
        "退休前每年淨儲蓄（元）", min_value=0, value=780_000, step=10_000
    )
    annual_expense = st.number_input(
        "退休後年支出（今日幣值，元）", min_value=0, value=492_000, step=10_000
    )
    inflation_rate = st.slider("通膨率", 0.0, 0.06, 0.02, 0.005)
    pre_retirement_return = st.slider("退休前投資報酬率", 0.0, 0.12, 0.06, 0.005)
    post_retirement_return = st.slider("退休後投資報酬率", 0.0, 0.10, 0.045, 0.005)

    st.header("Layer 2｜勞退新制")
    pension_current_balance = st.number_input(
        "目前勞退個人專戶餘額（元）", min_value=0, value=150_000, step=10_000
    )
    pension_contribution_base = st.number_input(
        "每月提繳工資（元）", min_value=0, value=60_000, step=1_000
    )
    pension_contribution_rate = st.slider("提繳率（雇主6%＋自提）", 0.06, 0.12, 0.12, 0.01)
    pension_return = st.slider("勞退基金假設年化報酬率", 0.0, 0.10, 0.04, 0.005)
    pension_take_as = st.radio("60歲後怎麼領", ["一次領", "月退"], horizontal=True)
    pension_unlock_age = 60

    st.header("Layer 3｜勞保老年給付")
    insurance_avg_salary = st.number_input(
        "平均月投保薪資（元）", min_value=0, value=45_800, step=1_000
    )
    insurance_years = st.number_input("預計請領時年資（年）", min_value=0.0, value=25.0, step=0.5)
    insurance_claim_age = st.selectbox("勞保請領年齡", [60, 61, 62, 63, 64, 65], index=0)

# ----------------------------------------------------------------------
# 人生事件面板
# ----------------------------------------------------------------------
st.subheader("人生事件")
st.caption("買房頭期款、旅遊基金、轉職降薪…任何時間點都可以插入，不影響核心計算邏輯。")

with st.form("add_event_form", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([1, 3, 2, 1])
    ev_age = c1.number_input("年齡", 18, 110, current_age, key="new_age")
    ev_label = c2.text_input("事件名稱", key="new_label", placeholder="例如：買房自備款")
    ev_amount = c3.number_input("金額（支出為負）", value=-100_000, step=10_000, key="new_amount")
    ev_recurring = c4.checkbox("每年重複", key="new_recurring")
    submitted = st.form_submit_button("＋ 新增事件")
    if submitted and ev_label:
        st.session_state.life_events.append(
            {"age": ev_age, "label": ev_label, "amount": ev_amount,
             "recurring": ev_recurring, "end_age": None}
        )

if st.session_state.life_events:
    header = st.columns([1, 3, 2, 1, 1])
    for col, text in zip(header, ["年齡", "事件名稱", "金額", "頻率", ""]):
        col.markdown(f"**{text}**")
    for i, ev in enumerate(sorted(st.session_state.life_events, key=lambda e: e["age"])):
        cols = st.columns([1, 3, 2, 1, 1])
        cols[0].write(f"{ev['age']}歲")
        cols[1].write(ev["label"])
        cols[2].write(f"{ev['amount']:,.0f} 元")
        cols[3].write("每年" if ev["recurring"] else "單次")
        if cols[4].button("刪除", key=f"del_{ev['age']}_{ev['label']}_{i}"):
            st.session_state.life_events.remove(ev)
            st.rerun()
else:
    st.info("目前沒有人生事件，資產走勢會是最單純的儲蓄→提領曲線。")

life_events_objs = [
    LifeEvent(
        age=e["age"], label=e["label"], amount=e["amount"],
        recurring=e["recurring"], end_age=e["end_age"],
    )
    for e in st.session_state.life_events
]

# ----------------------------------------------------------------------
# 計算
# ----------------------------------------------------------------------
years_to_unlock = max(0, pension_unlock_age - current_age)
labor_pension_at_60 = project_labor_pension_account(
    current_balance=pension_current_balance,
    years_to_unlock=years_to_unlock,
    monthly_contribution_base=pension_contribution_base,
    contribution_rate=pension_contribution_rate,
    annual_return=pension_return,
)

# 「月退」需要一個月給付金額：用簡化年金因子（平均餘命20年估算，之後可細化）
ANNUITY_YEARS_ESTIMATE = 20
pension_monthly_if_annuity = labor_pension_at_60 / (ANNUITY_YEARS_ESTIMATE * 12)

labor_insurance_monthly = calc_labor_insurance_monthly_pension(
    avg_monthly_insured_salary=insurance_avg_salary,
    years_of_service=insurance_years,
    claim_age=insurance_claim_age,
)

sim = simulate_lifetime(
    current_age=current_age,
    retirement_age=retirement_age,
    death_age=death_age,
    current_layer1_balance=current_layer1_balance,
    annual_savings_pre_retirement=annual_savings_pre_retirement,
    annual_expense_today=annual_expense,
    inflation_rate=inflation_rate,
    pre_retirement_return=pre_retirement_return,
    post_retirement_return=post_retirement_return,
    pension_unlock_age=pension_unlock_age,
    labor_pension_lump_sum=labor_pension_at_60,
    labor_pension_take_as="lump_sum" if pension_take_as == "一次領" else "monthly",
    labor_pension_monthly=pension_monthly_if_annuity,
    labor_insurance_claim_age=insurance_claim_age,
    labor_insurance_monthly=labor_insurance_monthly,
    life_events=life_events_objs,
)

# ----------------------------------------------------------------------
# 結果
# ----------------------------------------------------------------------
st.divider()
col1, col2, col3, col4 = st.columns(4)
retirement_record = next((r for r in sim.records if r.age == retirement_age), None)
col1.metric(
    f"{retirement_age}歲退休時資產",
    f"{retirement_record.balance_end:,.0f} 元" if retirement_record else "—",
)
col2.metric("60歲勞退估計累積", f"{labor_pension_at_60:,.0f} 元")
col3.metric(f"勞保月退（{insurance_claim_age}歲請領）", f"{labor_insurance_monthly:,.0f} 元/月")
col4.metric(
    "模擬結果",
    "✅ 撐到終點" if sim.success else f"❌ {sim.depleted_at_age}歲歸零",
)

ages = [r.age for r in sim.records]
balances = [r.balance_end for r in sim.records]

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=ages, y=balances, mode="lines", name="自由資產餘額",
        line=dict(width=3), fill="tozeroy",
    )
)
fig.add_vline(
    x=retirement_age, line_dash="dash", line_color="orange",
    annotation_text=f"{retirement_age}歲｜退休", annotation_position="top",
)
fig.add_vline(
    x=pension_unlock_age, line_dash="dash", line_color="gray",
    annotation_text="60歲｜勞退/勞保解鎖", annotation_position="bottom",
)
for ev in life_events_objs:
    if not ev.recurring:
        fig.add_vline(x=ev.age, line_dash="dot", line_color="crimson", opacity=0.5)
if not sim.success:
    fig.add_vline(
        x=sim.depleted_at_age, line_dash="dot", line_color="red",
        annotation_text="資產歸零", annotation_position="top",
    )
fig.update_layout(
    title="全時間軸資產走勢（固定報酬率）",
    xaxis_title="年齡", yaxis_title="自由資產餘額（元）",
    height=480,
)
st.plotly_chart(fig, use_container_width=True)

with st.expander("查看逐年明細"):
    st.dataframe(
        {
            "年齡": ages,
            "階段": ["累積" if r.phase == "accumulation" else "提領" for r in sim.records],
            "投資成長": [round(r.investment_growth) for r in sim.records],
            "儲蓄/支出": [round(r.savings_or_expense) for r in sim.records],
            "勞退挹注": [round(r.labor_pension_inflow) for r in sim.records],
            "勞保挹注": [round(r.labor_insurance_inflow) for r in sim.records],
            "人生事件": [round(r.life_event_flow) for r in sim.records],
            "事件說明": [r.life_event_labels for r in sim.records],
            "期末餘額": [round(r.balance_end) for r in sim.records],
        },
        use_container_width=True,
    )

st.caption(
    "以上為固定報酬率版本（Phase 1）；勞退/勞保相關數字仍為示範假設值，請替換成你查到的真實資料。"
)

# ----------------------------------------------------------------------
# Phase 3：情境比較
# ----------------------------------------------------------------------
st.divider()
st.header("情境比較（Phase 3）")
st.caption("把目前左側設定另存成一個情境，可以同時比較多組情境（例如不同退休年齡、有無買房）。")

if "saved_scenarios" not in st.session_state:
    st.session_state.saved_scenarios = {}

save_col1, save_col2 = st.columns([3, 1])
scenario_name = save_col1.text_input(
    "情境名稱", placeholder=f"例如：{retirement_age}歲退休"
)
if save_col2.button("💾 另存為情境", use_container_width=True) and scenario_name:
    st.session_state.saved_scenarios[scenario_name] = Scenario(
        name=scenario_name,
        current_age=current_age,
        retirement_age=retirement_age,
        death_age=death_age,
        current_layer1_balance=current_layer1_balance,
        annual_savings_pre_retirement=annual_savings_pre_retirement,
        annual_expense_today=annual_expense,
        inflation_rate=inflation_rate,
        pre_retirement_return=pre_retirement_return,
        post_retirement_return=post_retirement_return,
        pension_unlock_age=pension_unlock_age,
        labor_pension_lump_sum=labor_pension_at_60,
        labor_pension_take_as="lump_sum" if pension_take_as == "一次領" else "monthly",
        labor_pension_monthly=pension_monthly_if_annuity,
        labor_insurance_claim_age=insurance_claim_age,
        labor_insurance_monthly=labor_insurance_monthly,
        life_events=list(life_events_objs),
    )
    st.success(f"已儲存情境「{scenario_name}」")

if st.session_state.saved_scenarios:
    selected_names = st.multiselect(
        "選擇要比較的情境",
        list(st.session_state.saved_scenarios.keys()),
        default=list(st.session_state.saved_scenarios.keys()),
    )
    if st.button("🗑 清空已儲存情境"):
        st.session_state.saved_scenarios = {}
        st.rerun()

    if selected_names:
        selected_scenarios = [st.session_state.saved_scenarios[n] for n in selected_names]
        compare_results = compare_scenarios(selected_scenarios)

        compare_fig = go.Figure()
        summary_rows = []
        for name, res in compare_results.items():
            ages_c = [r.age for r in res.records]
            balances_c = [r.balance_end for r in res.records]
            compare_fig.add_trace(go.Scatter(x=ages_c, y=balances_c, mode="lines", name=name))
            summary_rows.append(
                {
                    "情境": name,
                    "結果": "✅ 撐到終點" if res.success else f"❌ {res.depleted_at_age}歲歸零",
                    "終點資產": f"{res.records[-1].balance_end:,.0f} 元",
                }
            )
        compare_fig.add_hline(y=0, line_dash="dot", line_color="red")
        compare_fig.update_layout(
            title="情境比較｜資產走勢",
            xaxis_title="年齡", yaxis_title="自由資產餘額（元）",
            height=480,
        )
        st.plotly_chart(compare_fig, use_container_width=True)
        st.dataframe(summary_rows, use_container_width=True)
else:
    st.info("尚未儲存任何情境，調整左側參數後按「另存為情境」開始比較。")

# ----------------------------------------------------------------------
# Phase 2：蒙地卡羅模擬
# ----------------------------------------------------------------------
st.divider()
st.header("蒙地卡羅模擬（Phase 2）")
st.caption("把固定報酬率換成隨機抽樣，重複跑上千次，看資產撐到終點的機率有多高，而不是單一結果。")

mc_col1, mc_col2, mc_col3 = st.columns(3)
n_simulations = mc_col1.slider("模擬次數", 100, 3000, 1000, 100)
sampling_mode = mc_col2.selectbox(
    "抽樣模式", ["normal", "historical"],
    format_func=lambda x: "常態分布抽樣" if x == "normal" else "歷史區間重抽樣（示範資料，非真實台股數據）",
)
run_mc = mc_col3.button("▶ 執行蒙地卡羅模擬", use_container_width=True)

if sampling_mode == "normal":
    std_col1, std_col2 = st.columns(2)
    pre_stddev = std_col1.slider("退休前報酬率標準差", 0.0, 0.30, 0.15, 0.01)
    post_stddev = std_col2.slider("退休後報酬率標準差", 0.0, 0.30, 0.10, 0.01)
else:
    pre_stddev = post_stddev = 0.0
    st.info(
        "歷史區間重抽樣目前使用的是內建的示範報酬率清單，不是真實台股歷史數據，"
        "結果僅供驗證邏輯，之後會替換成真實資料。"
    )

if run_mc:
    with st.spinner(f"執行 {n_simulations} 次模擬中..."):
        mc_result = run_monte_carlo(
            n_simulations=n_simulations,
            current_age=current_age,
            retirement_age=retirement_age,
            death_age=death_age,
            current_layer1_balance=current_layer1_balance,
            annual_savings_pre_retirement=annual_savings_pre_retirement,
            annual_expense_today=annual_expense,
            inflation_rate=inflation_rate,
            pre_retirement_return_mean=pre_retirement_return,
            pre_retirement_return_stddev=pre_stddev,
            post_retirement_return_mean=post_retirement_return,
            post_retirement_return_stddev=post_stddev,
            return_sampling_mode=sampling_mode,
            pension_unlock_age=pension_unlock_age,
            labor_pension_lump_sum=labor_pension_at_60,
            labor_pension_take_as="lump_sum" if pension_take_as == "一次領" else "monthly",
            labor_pension_monthly=pension_monthly_if_annuity,
            labor_insurance_claim_age=insurance_claim_age,
            labor_insurance_monthly=labor_insurance_monthly,
            life_events=life_events_objs,
        )

    st.session_state["mc_result"] = mc_result

if "mc_result" in st.session_state:
    mc_result = st.session_state["mc_result"]

    r1, r2, r3 = st.columns(3)
    r1.metric("成功率（撐到終點）", f"{mc_result.success_rate:.1%}")
    r2.metric("最終資產中位數", f"{mc_result.final_percentile(50):,.0f} 元")
    r3.metric("最終資產 P10（悲觀情境）", f"{mc_result.final_percentile(10):,.0f} 元")

    p10_band = mc_result.percentile_band(10)
    p50_band = mc_result.percentile_band(50)
    p90_band = mc_result.percentile_band(90)

    fan_fig = go.Figure()
    fan_fig.add_trace(go.Scatter(
        x=mc_result.ages, y=p90_band, mode="lines",
        line=dict(width=0), showlegend=False,
    ))
    fan_fig.add_trace(go.Scatter(
        x=mc_result.ages, y=p10_band, mode="lines",
        line=dict(width=0), fill="tonexty", fillcolor="rgba(99,110,250,0.2)",
        name="P10–P90 區間",
    ))
    fan_fig.add_trace(go.Scatter(
        x=mc_result.ages, y=p50_band, mode="lines",
        line=dict(width=3), name="中位數走勢",
    ))
    fan_fig.add_hline(y=0, line_dash="dot", line_color="red")
    fan_fig.add_vline(
        x=retirement_age, line_dash="dash", line_color="orange",
        annotation_text=f"{retirement_age}歲｜退休",
    )
    fan_fig.update_layout(
        title=f"{mc_result.n_simulations}次模擬｜資產走勢機率帶（P10–P50–P90）",
        xaxis_title="年齡", yaxis_title="自由資產餘額（元）",
        height=480,
    )
    st.plotly_chart(fan_fig, use_container_width=True)

    st.caption(
        "區間帶越窄代表結果越穩定；若P10線觸及0以下，代表悲觀情境下資產會提前歸零。"
    )
