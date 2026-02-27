#!/usr/bin/env python3
"""Test 16: EventSource push-triggered triage latency.

Validates PUSH-06: triage latency under 10 seconds via push notification.

Prerequisites:
- Mailroom service running with EventSource push enabled
- Fastmail account with screener mailbox and triage labels configured
- A test sender email in the screener mailbox

Steps:
1. Connect to JMAP session and verify eventSourceUrl is available
2. Check the health endpoint for SSE connection status
3. Provide manual test instructions for latency measurement
4. Run automated health monitoring loop to detect poll activity

Run: python human-tests/test_16_eventsource_push.py
"""

import os
import sys
import time

import httpx


def main():
    token = os.environ.get("MAILROOM_JMAP_TOKEN")
    if not token:
        print("ERROR: MAILROOM_JMAP_TOKEN not set")
        sys.exit(1)

    print("=" * 60)
    print("Test 16: EventSource Push-Triggered Triage Latency")
    print("=" * 60)

    # Step 1: Connect to JMAP session
    print("\n1. Connecting to JMAP session...")
    with httpx.Client() as http:
        resp = http.get(
            "https://api.fastmail.com/jmap/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        session = resp.json()

    account_id = session["primaryAccounts"]["urn:ietf:params:jmap:mail"]
    event_source_url = session.get("eventSourceUrl")

    print(f"   Account: {account_id}")
    print(f"   EventSource URL: {event_source_url or 'NOT AVAILABLE'}")

    if not event_source_url:
        print("\n   WARNING: No eventSourceUrl in session. Push not available.")
        print("   This test requires EventSource support.")
        sys.exit(1)

    # Step 2: Check health endpoint for SSE status
    print("\n2. Checking service health endpoint...")
    try:
        health_resp = httpx.get("http://localhost:8080/healthz", timeout=5.0)
        health = health_resp.json()
        print(f"   Service status: {health.get('status')}")
        sse_info = health.get("eventsource", {})
        print(f"   SSE status: {sse_info.get('status')}")
        print(f"   SSE connected since: {sse_info.get('connected_since')}")
        print(f"   SSE reconnect count: {sse_info.get('reconnect_count')}")
    except Exception as e:
        print(f"   WARNING: Could not reach health endpoint: {e}")
        print("   Make sure the Mailroom service is running.")

    # Step 3: Instructions for manual test
    print("\n3. Manual latency test:")
    print("   a. Open Fastmail on your phone")
    print("   b. Find an email in the Screener mailbox")
    print("   c. Apply a triage label (e.g., @ToFeed)")
    print("   d. Watch the service logs for 'poll_completed trigger=push'")
    print("   e. The triage should complete within 10 seconds")
    print()
    print("   Expected log output:")
    print('     {"event": "poll_completed", "trigger": "push", ...}')
    print()
    print("   If you see trigger=fallback, the SSE connection may not be working.")
    print()

    # Step 4: Optional automated timing loop
    print("4. Automated monitoring (press Ctrl+C to stop):")
    print("   Polling health endpoint every 2 seconds to detect triage activity...")
    print()

    try:
        last_poll_time = None
        while True:
            try:
                health_resp = httpx.get(
                    "http://localhost:8080/healthz", timeout=5.0
                )
                health = health_resp.json()
                age = health.get("last_poll_age_seconds", 0)
                sse = health.get("eventsource", {})

                # Detect a fresh poll (age resets)
                if age < 5 and last_poll_time != age:
                    print(
                        f"   POLL DETECTED - age: {age}s, "
                        f"SSE: {sse.get('status')}"
                    )
                    last_poll_time = age
            except Exception:
                pass
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n   Monitoring stopped.")

    print("\nDone.")


if __name__ == "__main__":
    main()
