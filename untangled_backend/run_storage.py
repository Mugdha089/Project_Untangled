"""SQLite persistence for completed UNTANGLE processing runs."""

from __future__ import annotations

import json
import hashlib
import secrets
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent / "data" / "untangle.sqlite3"


class RunNotFoundError(Exception):
    """Raised when a requested processing run does not exist."""


class ClarificationNotFoundError(Exception):
    """Raised when a clarification does not belong to a processing run."""


class ClarificationAlreadyResolvedError(Exception):
    """Raised when a completed clarification is submitted again."""


def database_path() -> Path:
    """Return the configured database path, creating no files by itself."""
    configured = os.environ.get("UNTANGLE_DB_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_DATABASE_PATH


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        _create_schema(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            pdf_filename TEXT NOT NULL,
            excel_filename TEXT NOT NULL,
            pdf_bytes BLOB NOT NULL,
            excel_bytes BLOB NOT NULL,
            result_json TEXT NOT NULL
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(processing_runs)")}
    if "owner_id" not in columns:
        # Phase 1 runs remain ownerless and are intentionally inaccessible after auth.
        connection.execute("ALTER TABLE processing_runs ADD COLUMN owner_id TEXT")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL, role TEXT NOT NULL
        )"""
    )
    connection.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS clarification_decisions (
            run_id TEXT NOT NULL REFERENCES processing_runs(run_id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            selected_option TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'unresolved', 'resolved')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (run_id, item_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_runs_created_at "
        "ON processing_runs(created_at DESC)"
    )


def initialize_database() -> None:
    """Create the configured schema; safe to call on each app startup."""
    with _connection() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (os.getenv("UNTANGLE_DEMO_EMAIL", "demo@untangle.local").strip().lower(),)).fetchone() is None:
            create_user(
                os.getenv("UNTANGLE_DEMO_EMAIL", "demo@untangle.local"),
                os.getenv("UNTANGLE_DEMO_PASSWORD", "untangle-demo-2026"),
                full_name="Demo Engineer", role="Process Engineer", connection=connection,
            )
        connection.execute(
            "INSERT OR IGNORE INTO app_settings(key, value) VALUES ('token_secret', ?)",
            (secrets.token_hex(32),),
        )


PASSWORD_ITERATIONS = 600_000


def _password_fields(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return salt.hex(), hashed.hex()


def create_user(email: str, password: str, *, full_name: str, role: str, connection: sqlite3.Connection | None = None, user_id: str | None = None) -> dict[str, str]:
    email = email.strip().lower()
    salt, password_hash = _password_fields(password)
    values = (user_id or secrets.token_hex(16), email, salt, password_hash, full_name, role)
    if connection is not None:
        connection.execute("INSERT INTO users(user_id,email,password_salt,password_hash,full_name,role) VALUES(?,?,?,?,?,?)", values)
    else:
        with _connection() as conn:
            conn.execute("INSERT INTO users(user_id,email,password_salt,password_hash,full_name,role) VALUES(?,?,?,?,?,?)", values)
    return {"user_id": values[0], "email": email, "full_name": full_name, "role": role}


def find_user(email: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    return dict(row) if row else None


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    import hmac
    _, candidate = _password_fields(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, hash_hex)


def auth_secret() -> bytes:
    with _connection() as connection:
        row = connection.execute("SELECT value FROM app_settings WHERE key='token_secret'").fetchone()
        if row is None:
            secret = secrets.token_hex(32)
            connection.execute("INSERT INTO app_settings(key,value) VALUES('token_secret',?)", (secret,))
            return bytes.fromhex(secret)
        return bytes.fromhex(row["value"])


def save_run(
    result: dict[str, Any],
    *,
    pdf_filename: str,
    excel_filename: str,
    pdf_bytes: bytes,
    excel_bytes: bytes,
    owner_id: str,
) -> None:
    """Persist the response, uploads, and initial clarification rows atomically."""
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    run_id = result["run_id"]
    created_at = result["created_at"]
    with _connection() as connection:
        connection.execute(
            """INSERT INTO processing_runs
               (run_id, created_at, pdf_filename, excel_filename, pdf_bytes, excel_bytes, result_json, owner_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                created_at,
                pdf_filename,
                excel_filename,
                sqlite3.Binary(pdf_bytes),
                sqlite3.Binary(excel_bytes),
                serialized,
                owner_id,
            ),
        )
        now = datetime.now(timezone.utc).isoformat()
        connection.executemany(
            """INSERT INTO clarification_decisions
               (run_id, item_id, selected_option, status, updated_at)
               VALUES (?, ?, NULL, 'pending', ?)""",
            [(run_id, item["id"], now) for item in result["clarification_queue"]],
        )


def list_runs(owner_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent run metadata and KPI summaries."""
    with _connection() as connection:
        rows = connection.execute(
            """SELECT run_id, created_at, pdf_filename, excel_filename, result_json
               FROM processing_runs WHERE owner_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (owner_id, limit),
        ).fetchall()
    runs = []
    for row in rows:
        result = json.loads(row["result_json"])
        runs.append(
            {
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "pdf_filename": row["pdf_filename"],
                "excel_filename": row["excel_filename"],
                "kpis": result["kpis"],
            }
        )
    return runs


def get_run(run_id: str, owner_id: str) -> dict[str, Any] | None:
    """Return a saved run with its current clarification decisions."""
    with _connection() as connection:
        row = connection.execute(
            "SELECT result_json FROM processing_runs WHERE run_id = ? AND owner_id = ?", (run_id, owner_id)
        ).fetchone()
        if row is None:
            return None
        result = json.loads(row["result_json"])
        decisions = connection.execute(
            """SELECT item_id, selected_option, status, updated_at
               FROM clarification_decisions WHERE run_id = ? ORDER BY item_id""",
            (run_id,),
        ).fetchall()

    decision_by_id = {item["item_id"]: dict(item) for item in decisions}
    for clarification in result["clarification_queue"]:
        decision = decision_by_id.get(clarification["id"])
        if decision:
            clarification["status"] = decision["status"]
            if decision["selected_option"] is not None:
                clarification["selected_option"] = decision["selected_option"]
    result["clarification_decisions"] = [dict(item) for item in decisions if item["selected_option"]]
    return result


def get_run_files(run_id: str, owner_id: str) -> dict[str, Any] | None:
    """Return saved upload bytes and filenames for source-file restoration."""
    with _connection() as connection:
        row = connection.execute(
            """SELECT pdf_filename, excel_filename, pdf_bytes, excel_bytes
               FROM processing_runs WHERE run_id = ? AND owner_id = ?""",
            (run_id, owner_id),
        ).fetchone()
    return dict(row) if row else None


def record_decision(
    run_id: str,
    item_id: str,
    selected_option: str,
    status: str,
    result: dict[str, Any],
    owner_id: str,
) -> None:
    """Atomically persist one decision and the updated run result."""
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        existing = connection.execute(
            """SELECT d.status FROM clarification_decisions d
               JOIN processing_runs r ON r.run_id=d.run_id
               WHERE d.run_id = ? AND d.item_id = ? AND r.owner_id = ?""",
            (run_id, item_id, owner_id),
        ).fetchone()
        if existing is None:
            run_exists = connection.execute(
                "SELECT 1 FROM processing_runs WHERE run_id = ? AND owner_id = ?", (run_id, owner_id)
            ).fetchone()
            if run_exists is None:
                raise RunNotFoundError(run_id)
            raise ClarificationNotFoundError(item_id)
        if existing["status"] == "resolved":
            raise ClarificationAlreadyResolvedError(item_id)
        connection.execute(
            """UPDATE clarification_decisions
               SET selected_option = ?, status = ?, updated_at = ?
               WHERE run_id = ? AND item_id = ?""",
            (selected_option, status, now, run_id, item_id),
        )
        cursor = connection.execute(
            "UPDATE processing_runs SET result_json = ? WHERE run_id = ? AND owner_id = ?",
            (serialized, run_id, owner_id),
        )
        if cursor.rowcount != 1:
            raise RunNotFoundError(run_id)
