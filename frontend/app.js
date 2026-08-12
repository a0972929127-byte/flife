// app.js — Flife 前端邏輯
// 匿名裝置ID + 呼叫 FastAPI 後端 + Chart.js 繪圖

// 部署後前後端同網域，預設用相對路徑（同源）即可。
// 如果你想在本機把前端跟後端分開跑（例如各自用不同port開發），
// 可以在 index.html 載入 app.js 之前加一行：
//   <script>window.FLIFE_API_BASE = "http://localhost:8000";</script>
const API_BASE = window.FLIFE_API_BASE || "";

// ------------------------------------------------------------------
// 匿名裝置ID：第一次開啟時產生，存在 localStorage，不需要登入。
// 換裝置/清瀏覽器資料會遺失，之後可以加「還原代碼」機制找回。
// ------------------------------------------------------------------
function getDeviceId() {
  let id = localStorage.getItem("flife_device_id");
  if (!id) {
    id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
    localStorage.setItem("flife_device_id", id);
  }
  return id;
}
const DEVICE_ID = getDeviceId();

// ------------------------------------------------------------------
// 人生事件（存在記憶體，送出試算時一併打包）
// ------------------------------------------------------------------
let lifeEvents = [
  { age: 31, label: "旅遊基金(第1年)", amount: -100000, recurring: false, end_age: null },
  { age: 32, label: "旅遊基金(第2年)", amount: -100000, recurring: false, end_age: null },
  { age: 33, label: "旅遊基金(第3年)", amount: -100000, recurring: false, end_age: null },
  { age: 45, label: "買房自備款(示範金額)", amount: -3000000, recurring: false, end_age: null },
];

function renderEventTable() {
  const tbody = document.getElementById("event_list");
  tbody.innerHTML = "";
  [...lifeEvents].sort((a, b) => a.age - b.age).forEach((ev, sortedIdx) => {
    const realIdx = lifeEvents.indexOf(ev);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${ev.age}歲</td>
      <td>${ev.label}</td>
      <td>${ev.amount.toLocaleString()} 元</td>
      <td>${ev.recurring ? "每年" : "單次"}</td>
      <td><button data-idx="${realIdx}" class="del-event">刪除</button></td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll(".del-event").forEach((btn) => {
    btn.addEventListener("click", () => {
      lifeEvents.splice(Number(btn.dataset.idx), 1);
      renderEventTable();
    });
  });
}

document.getElementById("add_event_btn").addEventListener("click", () => {
  const age = Number(document.getElementById("ev_age").value);
  const label = document.getElementById("ev_label").value.trim();
  const amount = Number(document.getElementById("ev_amount").value);
  const recurring = document.getElementById("ev_recurring").checked;
  if (!label) return;
  lifeEvents.push({ age, label, amount, recurring, end_age: null });
  document.getElementById("ev_label").value = "";
  renderEventTable();
});

// ------------------------------------------------------------------
// 滑桿數值即時顯示
// ------------------------------------------------------------------
function bindRangeDisplay(id, suffixFn) {
  const el = document.getElementById(id);
  const out = document.getElementById(id + "_val");
  const update = () => (out.textContent = suffixFn(Number(el.value)));
  el.addEventListener("input", update);
  update();
}
bindRangeDisplay("inflation_rate", (v) => `${(v * 100).toFixed(1)}%`);
bindRangeDisplay("pre_retirement_return", (v) => `${(v * 100).toFixed(1)}%`);
bindRangeDisplay("post_retirement_return", (v) => `${(v * 100).toFixed(1)}%`);
bindRangeDisplay("pension_contribution_rate", (v) => `${(v * 100).toFixed(0)}%`);
bindRangeDisplay("pension_return", (v) => `${(v * 100).toFixed(1)}%`);

// ------------------------------------------------------------------
// 從表單組出 simulate 用的參數物件
// ------------------------------------------------------------------
async function projectPension() {
  const currentAge = Number(document.getElementById("current_age").value);
  const yearsToUnlock = Math.max(0, 60 - currentAge);
  const res = await fetch(`${API_BASE}/api/labor-pension-projection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_balance: Number(document.getElementById("pension_current_balance").value),
      years_to_unlock: yearsToUnlock,
      monthly_contribution_base: Number(document.getElementById("pension_contribution_base").value),
      contribution_rate: Number(document.getElementById("pension_contribution_rate").value),
      annual_return: Number(document.getElementById("pension_return").value),
    }),
  });
  const data = await res.json();
  return data.projected_balance_at_unlock;
}

async function projectInsurance() {
  const res = await fetch(`${API_BASE}/api/labor-insurance-pension`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      avg_monthly_insured_salary: Number(document.getElementById("insurance_avg_salary").value),
      years_of_service: Number(document.getElementById("insurance_years").value),
      claim_age: Number(document.getElementById("insurance_claim_age").value),
    }),
  });
  const data = await res.json();
  return data.monthly_pension;
}

async function buildParams() {
  const laborPensionLumpSum = await projectPension();
  const laborInsuranceMonthly = await projectInsurance();
  return {
    current_age: Number(document.getElementById("current_age").value),
    retirement_age: Number(document.getElementById("retirement_age").value),
    death_age: Number(document.getElementById("death_age").value),
    current_layer1_balance: Number(document.getElementById("current_layer1_balance").value),
    annual_savings_pre_retirement: Number(document.getElementById("annual_savings_pre_retirement").value),
    annual_expense_today: Number(document.getElementById("annual_expense_today").value),
    inflation_rate: Number(document.getElementById("inflation_rate").value),
    pre_retirement_return: Number(document.getElementById("pre_retirement_return").value),
    post_retirement_return: Number(document.getElementById("post_retirement_return").value),
    pension_unlock_age: 60,
    labor_pension_lump_sum: laborPensionLumpSum,
    labor_pension_take_as: document.getElementById("pension_take_as").value,
    labor_pension_monthly: laborPensionLumpSum / (20 * 12), // 簡化年金因子，之後可細化
    labor_insurance_claim_age: Number(document.getElementById("insurance_claim_age").value),
    labor_insurance_monthly: laborInsuranceMonthly,
    life_events: lifeEvents,
  };
}

// ------------------------------------------------------------------
// 圖表
// ------------------------------------------------------------------
let mainChart, mcChart, compareChart;

function renderMainChart(records, retirementAge) {
  const ctx = document.getElementById("chart").getContext("2d");
  const ages = records.map((r) => r.age);
  const balances = records.map((r) => r.balance_end);
  if (mainChart) mainChart.destroy();
  mainChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: ages,
      datasets: [{
        label: "自由資產餘額",
        data: balances,
        borderColor: "#22d3ee",
        backgroundColor: "rgba(34,211,238,0.15)",
        fill: true,
        tension: 0.2,
        pointRadius: 0,
      }],
    },
    options: {
      scales: {
        x: { title: { display: true, text: "年齡", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
        y: { title: { display: true, text: "元", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
      },
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
    },
  });
}

function renderMcChart(ages, p10, p50, p90) {
  const ctx = document.getElementById("mc_chart").getContext("2d");
  if (mcChart) mcChart.destroy();
  mcChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: ages,
      datasets: [
        { label: "P90", data: p90, borderColor: "transparent", pointRadius: 0 },
        { label: "P10–P90 區間", data: p10, borderColor: "transparent",
          backgroundColor: "rgba(34,211,238,0.15)", fill: "-1", pointRadius: 0 },
        { label: "中位數", data: p50, borderColor: "#22d3ee", pointRadius: 0, fill: false, borderWidth: 2 },
      ],
    },
    options: {
      scales: {
        x: { title: { display: true, text: "年齡", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
        y: { title: { display: true, text: "元", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
      },
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
    },
  });
}

function renderCompareChart(datasetMap) {
  const ctx = document.getElementById("compare_chart").getContext("2d");
  if (compareChart) compareChart.destroy();
  const colors = ["#22d3ee", "#f472b6", "#4ade80", "#facc15", "#a78bfa"];
  const datasets = Object.entries(datasetMap).map(([name, d], i) => ({
    label: name,
    data: d.balances,
    borderColor: colors[i % colors.length],
    pointRadius: 0,
    fill: false,
  }));
  const ages = Object.values(datasetMap)[0]?.ages || [];
  compareChart = new Chart(ctx, {
    type: "line",
    data: { labels: ages, datasets },
    options: {
      scales: {
        x: { title: { display: true, text: "年齡", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
        y: { title: { display: true, text: "元", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
      },
      plugins: { legend: { labels: { color: "#e2e8f0" } } },
    },
  });
}

function metricHtml(value, label, cls = "") {
  return `<div class="metric"><div class="value ${cls}">${value}</div><div class="label">${label}</div></div>`;
}

// ------------------------------------------------------------------
// 執行試算
// ------------------------------------------------------------------
document.getElementById("simulate_btn").addEventListener("click", async () => {
  const btn = document.getElementById("simulate_btn");
  btn.textContent = "計算中...";
  btn.disabled = true;
  try {
    const params = await buildParams();
    const res = await fetch(`${API_BASE}/api/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });
    const data = await res.json();

    document.getElementById("result_section").hidden = false;
    const retirementRecord = data.records.find((r) => r.age === params.retirement_age);
    document.getElementById("metrics").innerHTML =
      metricHtml(
        retirementRecord ? `${Math.round(retirementRecord.balance_end).toLocaleString()} 元` : "—",
        `${params.retirement_age}歲退休時資產`
      ) +
      metricHtml(`${Math.round(params.labor_pension_lump_sum).toLocaleString()} 元`, "60歲勞退估計累積") +
      metricHtml(`${Math.round(params.labor_insurance_monthly).toLocaleString()} 元/月`, "勞保月退") +
      metricHtml(
        data.success ? "撐到終點" : `${data.depleted_at_age}歲歸零`,
        "模擬結果",
        data.success ? "ok" : "fail"
      );
    renderMainChart(data.records, params.retirement_age);
  } catch (err) {
    alert("試算失敗，請確認後端 API 是否啟動：" + err);
  } finally {
    btn.textContent = "▶ 執行試算";
    btn.disabled = false;
  }
});

// ------------------------------------------------------------------
// 蒙地卡羅
// ------------------------------------------------------------------
document.getElementById("run_mc_btn").addEventListener("click", async () => {
  const btn = document.getElementById("run_mc_btn");
  btn.textContent = "模擬中...";
  btn.disabled = true;
  try {
    const params = await buildParams();
    const mcParams = {
      ...params,
      n_simulations: 1000,
      pre_retirement_return_stddev: 0.15,
      post_retirement_return_stddev: 0.10,
      return_sampling_mode: "normal",
    };
    const res = await fetch(`${API_BASE}/api/monte-carlo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mcParams),
    });
    const data = await res.json();

    document.getElementById("mc_section").hidden = false;
    document.getElementById("mc_metrics").innerHTML =
      metricHtml(`${(data.success_rate * 100).toFixed(1)}%`, "成功率（撐到終點）",
        data.success_rate > 0.8 ? "ok" : "fail") +
      metricHtml(`${Math.round(data.final_p50).toLocaleString()} 元`, "最終資產中位數") +
      metricHtml(`${Math.round(data.final_p10).toLocaleString()} 元`, "最終資產 P10（悲觀）");
    renderMcChart(data.ages, data.p10_band, data.p50_band, data.p90_band);
  } catch (err) {
    alert("蒙地卡羅模擬失敗：" + err);
  } finally {
    btn.textContent = "▶ 執行蒙地卡羅模擬";
    btn.disabled = false;
  }
});

// ------------------------------------------------------------------
// 情境儲存 / 比較
// ------------------------------------------------------------------
async function loadScenarios() {
  const res = await fetch(`${API_BASE}/api/scenarios?device_id=${DEVICE_ID}`);
  const scenarios = await res.json();
  const tbody = document.getElementById("scenario_list");
  tbody.innerHTML = "";
  scenarios.forEach((s) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" class="scenario-check" value="${s.id}"></td>
      <td>${s.name}</td>
      <td>${new Date(s.created_at).toLocaleString()}</td>
      <td><button data-id="${s.id}" class="del-scenario">刪除</button></td>
    `;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll(".del-scenario").forEach((b) =>
    b.addEventListener("click", async () => {
      await fetch(`${API_BASE}/api/scenarios/${b.dataset.id}?device_id=${DEVICE_ID}`, { method: "DELETE" });
      loadScenarios();
    })
  );
}

document.getElementById("save_scenario_btn").addEventListener("click", async () => {
  const name = document.getElementById("scenario_name").value.trim();
  if (!name) return;
  const params = await buildParams();
  await fetch(`${API_BASE}/api/scenarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: DEVICE_ID, name, params }),
  });
  document.getElementById("scenario_name").value = "";
  loadScenarios();
});

document.getElementById("select_all_scenarios").addEventListener("change", (e) => {
  document.querySelectorAll(".scenario-check").forEach((cb) => (cb.checked = e.target.checked));
});

document.getElementById("compare_btn").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll(".scenario-check:checked")].map((cb) => cb.value);
  if (ids.length === 0) return;
  const res = await fetch(`${API_BASE}/api/scenarios/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_id: DEVICE_ID, scenario_ids: ids }),
  });
  const data = await res.json();
  renderCompareChart(data);
});

// ------------------------------------------------------------------
// 初始化
// ------------------------------------------------------------------
renderEventTable();
loadScenarios();

// PWA：註冊 service worker（離線快取靜態資源）
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch((err) => {
      console.warn("Service worker 註冊失敗：", err);
    });
  });
}
