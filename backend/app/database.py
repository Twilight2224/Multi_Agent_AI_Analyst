from __future__ import annotations

import sqlite3

from .config import settings


DEMO_CUSTOMERS = [
    (1, "Amina", "Enterprise", "active", "2024-01-15", 1200.0),
    (2, "Bekzod", "SMB", "churned", "2025-01-19", 220.0),
    (3, "Dilshod", "Enterprise", "active", "2023-11-03", 1900.0),
    (4, "Farida", "SMB", "churned", "2025-02-28", 180.0),
    (5, "Gulnoza", "Mid-market", "active", "2024-07-09", 720.0),
    (6, "Jasur", "SMB", "churned", "2025-03-17", 250.0),
    (7, "Kamola", "Enterprise", "active", "2025-01-11", 1400.0),
    (8, "Lola", "Mid-market", "churned", "2025-03-29", 640.0),
]


def initialize_database() -> None:
    path = settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, segment TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','churned')),
                signup_date TEXT NOT NULL, monthly_revenue REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS churn_events (
                id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL,
                churn_date TEXT NOT NULL, reason TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );
            """
        )
        if connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
            connection.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", DEMO_CUSTOMERS)
            connection.executemany(
                "INSERT INTO churn_events(customer_id, churn_date, reason) VALUES (?, ?, ?)",
                [(2, "2025-01-19", "Missing integration"), (4, "2025-02-28", "Price sensitivity"),
                 (6, "2025-03-17", "Missing integration"), (8, "2025-03-29", "Slow support response")],
            )


def database_schema() -> str:
    with sqlite3.connect(settings.database_path) as connection:
        rows = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return "\n".join(row[0] for row in rows)


def execute_readonly_sql(sql: str) -> str:
    normalized = sql.strip().rstrip(";")
    lowered = normalized.lower()
    forbidden = ("insert", "update", "delete", "drop", "alter", "create", "attach", "pragma", "replace", "vacuum")
    if not lowered.startswith(("select", "with")) or any(f" {word} " in f" {lowered} " for word in forbidden):
        raise ValueError("Only one read-only SELECT/CTE query is allowed.")
    if ";" in normalized:
        raise ValueError("Multiple SQL statements are not allowed.")
    with sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True) as connection:
        connection.set_authorizer(_readonly_authorizer)
        cursor = connection.execute(normalized)
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(100)
    return str({"columns": columns, "rows": rows})


def _readonly_authorizer(action: int, *_: object) -> int:
    readonly_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    return sqlite3.SQLITE_OK if action in readonly_actions else sqlite3.SQLITE_DENY
