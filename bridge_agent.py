"""
bridge_agent.py — Runs on the SAME machine/network as Tally.

Every few seconds it asks the bridge API (on Railway) "any jobs for me?",
forwards each job's XML to Tally's local XML server, and posts the
response back. Only outbound HTTPS calls — nothing needs to be opened
on your router or firewall.

Run it with:
    python bridge_agent.py

Keep it running in the background (see "run as a Windows service" note
at the bottom) so it survives reboots.
"""

import os
import time

import requests

# ---- Config: set these as environment variables, or edit the defaults below ----
BRIDGE_API_URL = os.environ.get("BRIDGE_API_URL", "https://your-bridge-api.up.railway.app")
BRIDGE_API_KEY = os.environ.get("BRIDGE_API_KEY", "change-me")
CLIENT_ID = os.environ.get("BRIDGE_CLIENT_ID", "default-client")
TALLY_URL = os.environ.get("TALLY_URL", "http://localhost:9000")
POLL_INTERVAL_SECONDS = float(os.environ.get("BRIDGE_POLL_INTERVAL", "2"))
# -----------------------------------------------------------------------------

HEADERS = {"X-Api-Key": BRIDGE_API_KEY}


def send_to_tally(xml_payload: str) -> str:
    """Forward one XML voucher/request to the local Tally XML server."""
    resp = requests.post(
        TALLY_URL,
        data=xml_payload.encode("utf-8"),
        headers={"Content-Type": "text/xml"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.text


def poll_once():
    resp = requests.get(
        f"{BRIDGE_API_URL}/jobs/pending",
        params={"client_id": CLIENT_ID},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    for job in jobs:
        job_id = job["job_id"]
        xml_payload = job["xml"]
        print(f"[bridge-agent] picked up job {job_id}, sending to Tally...")
        try:
            result = send_to_tally(xml_payload)
            requests.post(
                f"{BRIDGE_API_URL}/jobs/{job_id}/result",
                json={"result": result},
                headers=HEADERS,
                timeout=30,
            )
            print(f"[bridge-agent] job {job_id} done")
        except Exception as e:
            requests.post(
                f"{BRIDGE_API_URL}/jobs/{job_id}/result",
                json={"error": str(e)},
                headers=HEADERS,
                timeout=30,
            )
            print(f"[bridge-agent] job {job_id} FAILED: {e}")


def main():
    print(f"[bridge-agent] starting. client_id={CLIENT_ID}")
    print(f"[bridge-agent] bridge API: {BRIDGE_API_URL}")
    print(f"[bridge-agent] tally URL:  {TALLY_URL}")
    while True:
        try:
            poll_once()
        except Exception as e:
            print(f"[bridge-agent] poll error: {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# To run this permanently in the background on Windows (survives reboot):
#   1. Install NSSM (https://nssm.cc/download)
#   2. nssm install TallyBridgeAgent "C:\Path\to\python.exe" "C:\Path\to\bridge_agent.py"
#   3. nssm start TallyBridgeAgent
# ---------------------------------------------------------------------------
