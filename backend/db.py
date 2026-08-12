"""
db.py — Flife 情境儲存（本機 SQLite / 正式環境 Postgres，同一份程式碼）

本機開發不用另外裝資料庫，預設用 SQLite（存在 backend/flife.db）。
部署時只要設定環境變數 DATABASE_URL（例如 Supabase 給的 Postgres 連線字串），
就會自動切換成 Postgres，其餘程式碼完全不用改。

不需要帳號密碼登入：每個使用者由前端產生的匿名 device_id 識別，
所有讀寫都要求 device_id 對得上，才能存取該筆情境——
這不是真正的身份驗證，只是避免隨便猜 scenario_id 就能讀到別人的資料。

⚠️ 純裝置綁定：換裝置、清瀏覽器資料，這組 device_id 就換了，
   舊資料撈不回來。之後如果要加「還原代碼」機制，只要多一張
   recovery_codes 表（code -> device_id）即可，不影響其他程式碼。
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_SQLITE_PATH = Path(__file__).parent / "flife.db"


def _build_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Supabase/Heroku風格的連線字串常是 postgres:// 開頭，
        # SQLAlchemy 2.x 需要 postgresql:// 開頭，這裡自動轉換。
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return create_engine(database_url, pool_pre_ping=True)
    return create_engine(f"sqlite:///{DEFAULT_SQLITE_PATH}")


engine = _build_engine()


def using_postgres() -> bool:
    return engine.url.get_backend_name().startswith("postgresql")


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS scenarios (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scenarios_device_id ON scenarios(device_id)"))


def save_scenario(device_id: str, name: str, params: Dict[str, Any]) -> str:
    scenario_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO scenarios (id, device_id, name, params_json, created_at) "
                "VALUES (:id, :device_id, :name, :params_json, :created_at)"
            ),
            {
                "id": scenario_id,
                "device_id": device_id,
                "name": name,
                "params_json": json.dumps(params),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    return scenario_id


def list_scenarios(device_id: str) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, name, params_json, created_at FROM scenarios "
                "WHERE device_id = :device_id ORDER BY created_at DESC"
            ),
            {"device_id": device_id},
        ).mappings().all()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "params": json.loads(r["params_json"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_scenario(scenario_id: str, device_id: str) -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, name, params_json, created_at FROM scenarios "
                "WHERE id = :id AND device_id = :device_id"
            ),
            {"id": scenario_id, "device_id": device_id},
        ).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "params": json.loads(row["params_json"]),
        "created_at": row["created_at"],
    }


def delete_scenario(scenario_id: str, device_id: str) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM scenarios WHERE id = :id AND device_id = :device_id"),
            {"id": scenario_id, "device_id": device_id},
        )
    return result.rowcount > 0
