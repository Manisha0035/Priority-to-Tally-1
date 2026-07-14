# Add this near your existing TALLY_URL config in app.py, then replace
# every `requests.post(TALLY_URL, data=xml, ...)` call with
# `send_to_tally_via_bridge(xml)` instead.

import time
import requests
import os

BRIDGE_API_URL = os.environ.get("BRIDGE_API_URL")          # e.g. https://your-bridge-api.up.railway.app
BRIDGE_API_KEY = os.environ.get("BRIDGE_API_KEY")
BRIDGE_CLIENT_ID = os.environ.get("BRIDGE_CLIENT_ID", "default-client")
BRIDGE_TIMEOUT_SECONDS = 45


def send_to_tally_via_bridge(xml_payload: str) -> str:
    """
    Sends XML to Tally through the bridge instead of calling TALLY_URL
    directly. Use this whenever the middleware app and Tally are on
    different networks/machines.
    """
    headers = {"X-Api-Key": BRIDGE_API_KEY}

    # 1. enqueue the job
    r = requests.post(
        f"{BRIDGE_API_URL}/jobs",
        json={"client_id": BRIDGE_CLIENT_ID, "xml": xml_payload},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    job_id = r.json()["job_id"]

    # 2. poll for the result
    deadline = time.time() + BRIDGE_TIMEOUT_SECONDS
    while time.time() < deadline:
        r = requests.get(f"{BRIDGE_API_URL}/jobs/{job_id}", headers=headers, timeout=15)
        r.raise_for_status()
        job = r.json()
        if job["status"] == "done":
            return job["result"]
        if job["status"] == "error":
            raise RuntimeError(f"Tally bridge error: {job['error']}")
        time.sleep(1)

    raise TimeoutError("Tally bridge: no response from local agent — is it running?")
