# Flife

台灣退休金三層資產（自由資產 / 勞退新制 / 勞保老年給付）試算工具，
含人生事件時間軸、蒙地卡羅模擬、多情境比較。

有兩種使用方式：

## 方式一：個人版（Streamlit，本機使用）

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 方式二：多人匿名版（FastAPI 後端 + 一起服務前端）

不需要登入，每個使用者用瀏覽器自動產生的匿名裝置ID區隔資料。
前端是純HTML/CSS/JS（沒有build流程），後端會直接把它一起服務出去，
**所以只需要部署一個地方**，就有一個網址可以分享給朋友。

**本機測試：**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
瀏覽器開 http://localhost:8000 就能看到完整介面（API也在同一個網址下的 `/api/...`）。
手機瀏覽器打開同一個網址後可以「加入主畫面」變成類App圖示。

**要分享給朋友（部署到公開網址）：**

專案裡已經準備好兩種平台的設定檔（`nixpacks.toml` 給 Railway、`render.yaml` 給 Render），
兩邊都會正確安裝 `backend/requirements.txt` 並啟動FastAPI（同時服務API和前端）。

**第一步（兩個平台都要）：把專案推上 GitHub**
1. 在 GitHub 開一個新的空白 repository（例如 `flife`）
2. 在專案根目錄執行：
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <你的repo網址>
   git push -u origin main
   ```

**選 Railway：**
1. 到 [railway.app](https://railway.app)，New Project → Deploy from GitHub repo，選你剛推上去的repo
2. Railway 會自動偵測到 `nixpacks.toml` 並照裡面的設定建置
3. 到專案的 Variables 分頁，新增 `DATABASE_URL`，貼上 Supabase 給的 Session pooler 連線字串
4. 部署完成後，Settings 分頁裡有個「Generate Domain」，按下去就會得到公開網址

**選 Render：**
1. 到 [render.com](https://render.com)，New → Web Service，選你的GitHub repo
2. Render 會偵測到 `render.yaml`，Build/Start指令會自動帶入，不用手動填
3. 部署前，在 Environment 分頁新增 `DATABASE_URL`，貼上連線字串
4. 部署完成後會直接給一個 `https://flife-xxxx.onrender.com` 這樣的網址

**⚠️ 部署後的注意事項：**
- 不管選哪個平台，記得`DATABASE_URL`要貼**Session pooler**版本的連線字串（不是Direct connection），細節見上面Supabase設定的討論——Session pooler走IPv4，跟這些平台的網路相容
- 純裝置綁定：換裝置、清瀏覽器資料，情境資料就找不回來了，之後可以加「還原代碼」機制（見 `backend/db.py` 註解）
- Render 的免費方案15分鐘沒人用會休眠，下次有人打開網址時要等約1分鐘喚醒；Railway 沒有這個問題，但免費額度用完後功能會受限（見前面討論）

**想在本機把前端跟後端分開開發**（例如各自用不同port）：
在 `frontend/index.html` 載入 `app.js` 之前加一行
`<script>window.FLIFE_API_BASE = "http://localhost:8000";</script>`，
再用 `python3 -m http.server 8080` 單獨跑前端即可。

## 專案結構

```
flife/
├── core/                          # 核心運算邏輯（與UI/後端完全解耦）
│   ├── pension_bridge_simulator.py    # 三層資產 + 人生事件 全時間軸模擬
│   ├── monte_carlo.py                 # 蒙地卡羅（常態分布 / 歷史重抽樣）
│   └── scenario.py                    # 多情境比較
├── app.py                         # 個人版 Streamlit 介面
├── backend/                       # 多人版 FastAPI 後端
│   ├── main.py                        # API 端點
│   ├── db.py                          # 匿名情境儲存（SQLite）
│   └── requirements.txt
├── frontend/                      # 多人版 PWA 前端（純HTML/JS，無需建置工具）
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.json
│   ├── service-worker.js
│   └── icon-192.png / icon-512.png
├── data/                          # Phase 2 起放歷史報酬率等靜態資料
└── requirements.txt                # 個人版(Streamlit)用
```

## 進度

- [x] Phase 0：核心模組（勞退推算 / 勞保推算，固定報酬率）
- [x] Phase 1：Streamlit 互動介面（個人版）
- [x] 核心升級：全時間軸模擬（累積期＋提領期合一）＋ 人生事件（LifeEvent）資料驅動引擎
- [x] Phase 2：蒙地卡羅（常態分布抽樣 + 歷史區間重抽樣兩種模式，成功率＋P10-P50-P90機率帶狀圖）
- [x] Phase 3：多情境比較（另存情境＋多選比較＋疊圖）
- [x] 多人匿名版：FastAPI 後端（已完整測試：模擬/蒙地卡羅/情境CRUD/裝置隔離）＋ 同伺服器直接服務PWA前端（單一部署網址）
- [x] 部署設定備妥：nixpacks.toml（Railway）、render.yaml（Render）、.gitignore、.env.example，皆已語法驗證
- [ ] 實際部署到公開網址（設定檔已備好，尚待推上GitHub並在平台上操作）
- [x] 資料庫雙模式支援：SQLite（本機預設）／ Postgres（設定 DATABASE_URL 自動切換，已用本機Postgres完整測試含裝置隔離邏輯，適配Supabase）
- [ ] 歷史區間重抽樣要換成真實台股/0050歷史數據（目前是示範用假清單，見 core/monte_carlo.py 頂部說明）
- [ ] 前端所有假設值待替換成真實勞退/勞保資料
- [ ] 還原代碼機制（跨裝置找回情境，選配）
