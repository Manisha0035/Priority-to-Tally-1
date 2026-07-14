"""
bridge_api.py — Job queue that sits on Railway between your Streamlit app
and the local agent running next to Tally.

Flow:
  1. Streamlit app POSTs an XML job here            -> /jobs
  2. Local agent polls here for pending jobs        -> /jobs/pending
  3. Local agent posts Tally's XML response back     -> /jobs/{id}/result
  4. Streamlit app polls here for the result         -> /jobs/{id}

No inbound connection to your local machine is ever needed — the agent
only makes outbound HTTPS calls to this service.
"""

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

API_KEY = os.environ.get("BRIDGE_API_KEY", "change-me")
DB_PATH = os.environ.get("BRIDGE_DB_PATH", "bridge.db")
JOB_TTL_SECONDS = 60 * 30  # stale jobs older than this are ignored by agent

app = FastAPI(title="Tally Bridge API")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                xml TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)


init_db()


def check_key(x_api_key: str | None):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


class NewJob(BaseModel):
    client_id: str
    xml: str


class JobResult(BaseModel):
    result: str | None = None
    error: str | None = None


@app.post("/jobs")
def create_job(job: NewJob, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    job_id = str(uuid.uuid4())
    now = time.time()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, client_id, xml, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (job_id, job.client_id, job.xml, now, now),
        )
    return {"job_id": job_id}


@app.get("/jobs/pending")
def get_pending(client_id: str, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    cutoff = time.time() - JOB_TTL_SECONDS
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, xml FROM jobs WHERE client_id = ? AND status = 'pending' AND created_at > ?",
            (client_id, cutoff),
        ).fetchall()
        # mark as picked so the agent doesn't grab the same job twice on the next poll
        for r in rows:
            conn.execute(
                "UPDATE jobs SET status = 'picked', updated_at = ? WHERE id = ?",
                (time.time(), r["id"]),
            )
    return {"jobs": [{"job_id": r["id"], "xml": r["xml"]} for r in rows]}


@app.post("/jobs/{job_id}/result")
def post_result(job_id: str, payload: JobResult, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    status = "error" if payload.error else "done"
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = ?, result = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, payload.result, payload.error, time.time(), job_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, x_api_key: str | None = Header(default=None)):
    check_key(x_api_key)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@app.get("/health")
def health():
    return {"ok": True}
