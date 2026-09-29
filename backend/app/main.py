import json
import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import pyodbc
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_HOST = os.getenv("DB_HOST", "mssql")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_NAME = os.getenv("DB_NAME", "master")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Your_strong_password123")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

SAMPLE_PAGES = [
    {
        "url": "https://news.example/home",
        "title": "News Home",
        "content": "Breaking stories, market updates, and top headlines.",
    },
    {
        "url": "https://news.example/tech",
        "title": "Tech",
        "content": "AI, cloud, and cybersecurity stories for technology readers.",
    },
    {
        "url": "https://news.example/sports",
        "title": "Sports",
        "content": "Scores, highlights, and upcoming fixtures.",
    },
    {
        "url": "https://news.example/finance",
        "title": "Finance",
        "content": "Portfolio, inflation, and macroeconomic coverage.",
    },
    {
        "url": "https://news.example/travel",
        "title": "Travel",
        "content": "Destination ideas, best season tips, and city guides.",
    },
]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)


class VisitCreate(BaseModel):
    user_id: int
    page_url: str = Field(min_length=5, max_length=500)
    page_title: str = Field(min_length=1, max_length=200)


app = FastAPI(title="Predictive Page Preload PoC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db_connection() -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_HOST},{DB_PORT};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def wait_for_db(max_attempts: int = 30, sleep_seconds: int = 2) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                return
        except pyodbc.Error:
            if attempt == max_attempts:
                raise
            time.sleep(sleep_seconds)


def bootstrap_schema() -> None:
    schema_sql = """
    IF OBJECT_ID('dbo.users', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.users (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(100) UNIQUE NOT NULL,
            created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
    END;

    IF OBJECT_ID('dbo.pages', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.pages (
            id INT IDENTITY(1,1) PRIMARY KEY,
            url NVARCHAR(500) UNIQUE NOT NULL,
            title NVARCHAR(200) NOT NULL,
            content NVARCHAR(MAX) NULL,
            created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
    END;

    IF OBJECT_ID('dbo.page_visits', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.page_visits (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            user_id INT NOT NULL,
            page_id INT NOT NULL,
            visited_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT FK_page_visits_users FOREIGN KEY (user_id) REFERENCES dbo.users(id),
            CONSTRAINT FK_page_visits_pages FOREIGN KEY (page_id) REFERENCES dbo.pages(id)
        );

        CREATE INDEX IX_page_visits_user_time ON dbo.page_visits (user_id, visited_at);
    END;

    IF OBJECT_ID('dbo.user_transition_models', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.user_transition_models (
            user_id INT PRIMARY KEY,
            model_type NVARCHAR(50) NOT NULL,
            model_payload NVARCHAR(MAX) NOT NULL,
            trained_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT FK_transition_models_users FOREIGN KEY (user_id) REFERENCES dbo.users(id)
        );
    END;

    IF OBJECT_ID('dbo.user_prediction_snapshots', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.user_prediction_snapshots (
            user_id INT NOT NULL,
            current_url NVARCHAR(500) NOT NULL,
            predictions_payload NVARCHAR(MAX) NOT NULL,
            generated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
            PRIMARY KEY (user_id, current_url),
            CONSTRAINT FK_prediction_snapshots_users FOREIGN KEY (user_id) REFERENCES dbo.users(id)
        );
    END;
    """

    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(schema_sql)
        conn.commit()


def seed_pages() -> None:
    with db_connection() as conn:
        cursor = conn.cursor()
        for page in SAMPLE_PAGES:
            cursor.execute(
                """
                MERGE dbo.pages AS target
                USING (SELECT ? AS url, ? AS title, ? AS content) AS source
                ON target.url = source.url
                WHEN MATCHED THEN
                    UPDATE SET title = source.title, content = source.content
                WHEN NOT MATCHED THEN
                    INSERT (url, title, content) VALUES (source.url, source.title, source.content);
                """,
                page["url"],
                page["title"],
                page["content"],
            )
        conn.commit()


def get_or_create_page(cursor: pyodbc.Cursor, page_url: str, page_title: str) -> int:
    cursor.execute("SELECT id FROM dbo.pages WHERE url = ?", page_url)
    row = cursor.fetchone()
    if row:
        cursor.execute("UPDATE dbo.pages SET title = ? WHERE id = ?", page_title, row[0])
        return int(row[0])

    cursor.execute(
        "INSERT INTO dbo.pages (url, title) OUTPUT INSERTED.id VALUES (?, ?)",
        page_url,
        page_title,
    )
    inserted = cursor.fetchone()
    return int(inserted[0])


def train_user_model(conn: pyodbc.Connection, user_id: int) -> dict[str, dict[str, float]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.url
        FROM dbo.page_visits pv
        INNER JOIN dbo.pages p ON p.id = pv.page_id
        WHERE pv.user_id = ?
        ORDER BY pv.visited_at ASC, pv.id ASC
        """,
        user_id,
    )
    sequence = [row[0] for row in cursor.fetchall()]
    transition_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for current_url, next_url in zip(sequence, sequence[1:]):
        transition_counts[current_url][next_url] += 1

    transition_probs: dict[str, dict[str, float]] = {}
    for current_url, next_counts in transition_counts.items():
        total = sum(next_counts.values())
        if total == 0:
            continue
        transition_probs[current_url] = {
            next_url: count / total for next_url, count in next_counts.items()
        }

    payload = json.dumps(transition_probs)
    cursor.execute(
        """
        MERGE dbo.user_transition_models AS target
        USING (SELECT ? AS user_id, ? AS model_type, ? AS model_payload) AS source
        ON target.user_id = source.user_id
        WHEN MATCHED THEN
            UPDATE SET model_type = source.model_type,
                       model_payload = source.model_payload,
                       trained_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN
            INSERT (user_id, model_type, model_payload)
            VALUES (source.user_id, source.model_type, source.model_payload);
        """,
        user_id,
        "markov_v1",
        payload,
    )
    conn.commit()
    return transition_probs


def load_user_model(user_id: int) -> dict[str, dict[str, float]]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT model_payload FROM dbo.user_transition_models WHERE user_id = ?",
            user_id,
        )
        row = cursor.fetchone()
        if not row:
            return {}
        return json.loads(row[0])


def load_user_page_visit_counts(user_id: int) -> dict[str, int]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.url, COUNT(*) AS visit_count
            FROM dbo.page_visits pv
            INNER JOIN dbo.pages p ON p.id = pv.page_id
            WHERE pv.user_id = ?
            GROUP BY p.url
            """,
            user_id,
        )
        rows = cursor.fetchall()
    return {row[0]: int(row[1]) for row in rows}


def store_prediction_snapshot(user_id: int, current_url: str, predictions: list[dict[str, Any]]) -> None:
    payload = json.dumps(predictions)
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            MERGE dbo.user_prediction_snapshots AS target
            USING (SELECT ? AS user_id, ? AS current_url, ? AS predictions_payload) AS source
            ON target.user_id = source.user_id AND target.current_url = source.current_url
            WHEN MATCHED THEN
                UPDATE SET predictions_payload = source.predictions_payload,
                           generated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (user_id, current_url, predictions_payload)
                VALUES (source.user_id, source.current_url, source.predictions_payload);
            """,
            user_id,
            current_url,
            payload,
        )
        conn.commit()


@app.on_event("startup")
def startup_event() -> None:
    wait_for_db()
    bootstrap_schema()
    seed_pages()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/pages")
def list_pages() -> list[dict[str, Any]]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, url, title FROM dbo.pages ORDER BY id")
        return [{"id": r[0], "url": r[1], "title": r[2]} for r in cursor.fetchall()]


@app.get("/api/users")
def list_users() -> list[dict[str, Any]]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, created_at FROM dbo.users ORDER BY id")
        rows = cursor.fetchall()
        return [{"id": r[0], "username": r[1], "created_at": r[2].isoformat()} for r in rows]


@app.post("/api/users")
def create_user(payload: UserCreate) -> dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dbo.users WHERE username = ?", payload.username)
        existing = cursor.fetchone()
        if existing:
            return {"id": int(existing[0]), "username": payload.username, "created": False}

        cursor.execute(
            "INSERT INTO dbo.users (username) OUTPUT INSERTED.id VALUES (?)",
            payload.username,
        )
        row = cursor.fetchone()
        conn.commit()
        return {"id": int(row[0]), "username": payload.username, "created": True}


@app.post("/api/visit")
def record_visit(payload: VisitCreate) -> dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM dbo.users WHERE id = ?", payload.user_id)
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="User not found")

        page_id = get_or_create_page(cursor, payload.page_url, payload.page_title)
        cursor.execute(
            "INSERT INTO dbo.page_visits (user_id, page_id) VALUES (?, ?)",
            payload.user_id,
            page_id,
        )
        conn.commit()

        model = train_user_model(conn, payload.user_id)

    return {
        "ok": True,
        "user_id": payload.user_id,
        "page_url": payload.page_url,
        "trained_states": len(model),
    }


@app.get("/api/history/{user_id}")
def get_user_history(user_id: int) -> list[dict[str, Any]]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP 100 pv.id, p.url, p.title, pv.visited_at
            FROM dbo.page_visits pv
            INNER JOIN dbo.pages p ON p.id = pv.page_id
            WHERE pv.user_id = ?
            ORDER BY pv.visited_at DESC, pv.id DESC
            """,
            user_id,
        )
        rows = cursor.fetchall()

    return [
        {
            "visit_id": r[0],
            "url": r[1],
            "title": r[2],
            "visited_at": r[3].isoformat(),
        }
        for r in rows
    ]


@app.get("/api/predict-next/{user_id}")
def predict_next(user_id: int, current_url: str, top_k: int = 3) -> dict[str, Any]:
    model = load_user_model(user_id)
    visit_counts = load_user_page_visit_counts(user_id)
    transitions = model.get(current_url, {})

    ranked = sorted(transitions.items(), key=lambda item: item[1], reverse=True)[:top_k]
    predictions = [
        {
            "url": url,
            "probability": prob,
            "visit_count": visit_counts.get(url, 0),
        }
        for url, prob in ranked
    ]
    predictions.sort(key=lambda item: (item["visit_count"], item["probability"]), reverse=True)
    store_prediction_snapshot(user_id, current_url, predictions)

    return {
        "user_id": user_id,
        "current_url": current_url,
        "predictions": predictions,
        "model_states": len(model),
    }


@app.get("/api/stored-prediction/{user_id}")
def stored_prediction(user_id: int, current_url: str) -> dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT predictions_payload, generated_at
            FROM dbo.user_prediction_snapshots
            WHERE user_id = ? AND current_url = ?
            """,
            user_id,
            current_url,
        )
        row = cursor.fetchone()

    if not row:
        return {"user_id": user_id, "current_url": current_url, "predictions": [], "generated_at": None}

    return {
        "user_id": user_id,
        "current_url": current_url,
        "predictions": json.loads(row[0]),
        "generated_at": row[1].isoformat(),
    }


@app.get("/api/page-content")
def page_content(page_url: str) -> dict[str, Any]:
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, content FROM dbo.pages WHERE url = ?", page_url)
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Page not found")

    return {"url": page_url, "title": row[0], "content": row[1] or "No content available."}
