"""Human test 14: JMAP EventSource Discovery (read-only, safe).

Connects to Fastmail's JMAP EventSource (SSE) endpoint and logs
real-time state change events. Use this to discover event patterns,
frequency, and payload shape for future push-based architecture.

Usage:
    python human-tests/test_14_eventsource.py              # listen for 60s
    python human-tests/test_14_eventsource.py --duration 120  # listen for 2 min
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx

from mailroom.clients.jmap import JMAPClient
from mailroom.core.config import MailroomSettings


def timestamp() -> str:
    """Return ISO 8601 timestamp with milliseconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]


def fetch_event_source_url(token: str, hostname: str = "api.fastmail.com") -> str:
    """Fetch the eventSourceUrl from the JMAP session endpoint."""
    resp = httpx.get(
        f"https://{hostname}/jmap/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    session = resp.json()
    url = session.get("eventSourceUrl")
    if not url:
        raise RuntimeError("Session response does not contain 'eventSourceUrl'")
    return url


def build_eventsource_url(base_url: str, types: str = "*", closeafter: str = "no", ping: int = 30) -> str:
    """Build the full EventSource URL per RFC 8620 section 7.3."""
    return f"{base_url}?types={types}&closeafter={closeafter}&ping={ping}"


def parse_sse_event(lines: list[str]) -> dict:
    """Parse accumulated SSE lines into an event dict.

    SSE format:
        event: <type>
        data: <payload>
        : <comment/keepalive>

    Returns dict with 'event', 'data', and/or 'comment' keys.
    """
    result: dict = {}
    data_lines: list[str] = []

    for line in lines:
        if line.startswith("event:"):
            result["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
        elif line.startswith("retry:"):
            result["retry"] = line[len("retry:"):].strip()
        elif line.startswith(":"):
            result["comment"] = line[1:].strip()

    if data_lines:
        raw_data = "\n".join(data_lines)
        try:
            result["data"] = json.loads(raw_data)
        except json.JSONDecodeError:
            result["data_raw"] = raw_data

    return result


def print_state_event(event: dict) -> None:
    """Pretty-print a parsed state change event.

    Fastmail wraps the RFC 8620 state data in an envelope:
        {"changed": {"accountId": {"TypeName": "state", ...}}, "type": "connect|change"}

    The RFC 8620 spec says data is: {"accountId": {"TypeName": "state", ...}}
    We handle both formats gracefully.
    """
    ts = timestamp()
    event_type = event.get("event", "unknown")
    data = event.get("data")

    # Detect Fastmail envelope format vs raw RFC format
    if isinstance(data, dict) and "changed" in data:
        # Fastmail envelope: {"changed": {acct: {types}}, "type": "connect|change"}
        subtype = data.get("type", "")
        print(f"[{ts}] event={event_type} type={subtype}")
        changed = data["changed"]
        if isinstance(changed, dict):
            for account_id, type_states in changed.items():
                print(f"  Account: {account_id}")
                if isinstance(type_states, dict):
                    for type_name, state_value in type_states.items():
                        print(f"    {type_name} -> \"{state_value}\"")
                else:
                    print(f"    {type_states}")
    elif isinstance(data, dict):
        # Raw RFC 8620 format: {"accountId": {"TypeName": "state"}}
        print(f"[{ts}] event={event_type}")
        for account_id, type_states in data.items():
            print(f"  Account: {account_id}")
            if isinstance(type_states, dict):
                for type_name, state_value in type_states.items():
                    print(f"    {type_name} -> \"{state_value}\"")
            else:
                print(f"    {type_states}")
    elif "data_raw" in event:
        print(f"[{ts}] event={event_type}")
        print(f"  Raw data: {event['data_raw']}")
    else:
        print(f"[{ts}] event={event_type} (no data)")

    if "retry" in event:
        print(f"  Retry: {event['retry']}ms")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="JMAP EventSource discovery: listen for SSE events from Fastmail"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="How many seconds to listen (default: 60)",
    )
    args = parser.parse_args()

    settings = MailroomSettings()
    token = settings.jmap_token

    # Step 1: Connect via JMAPClient to verify credentials
    print("Connecting to Fastmail JMAP session...")
    client = JMAPClient(token=token)
    client.connect()
    print(f"  Connected! Account ID: {client.account_id}")

    # Step 2: Fetch eventSourceUrl from raw session
    print("\nFetching EventSource URL from session...")
    event_source_base = fetch_event_source_url(token)
    print(f"  EventSource base URL: {event_source_base}")

    # Step 3: Build full URL per RFC 8620 section 7.3
    url = build_eventsource_url(event_source_base, types="*", closeafter="no", ping=30)
    print(f"  Full URL: {url}")

    # Step 4: Connect to SSE stream
    print(f"\nListening for EventSource events for {args.duration} seconds...")
    print("  Tip: Send yourself an email, apply a label, or move an email to see events.")
    print("  Press Ctrl+C to stop early.\n")

    state_events = 0
    ping_count = 0
    other_events = 0
    start_time = time.monotonic()

    current_lines: list[str] = []

    try:
        # Read timeout slightly exceeds ping interval (30s) + duration to allow clean exit
        read_timeout = float(args.duration + 35)
        with httpx.Client(timeout=httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)) as http:
            with http.stream(
                "GET",
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "text/event-stream",
                },
            ) as response:
                response.raise_for_status()
                print(f"[{timestamp()}] Connected to EventSource (HTTP {response.status_code})\n")

                for line in response.iter_lines():
                    elapsed = time.monotonic() - start_time
                    if elapsed >= args.duration:
                        break

                    # SSE: empty line = end of event
                    if line == "":
                        if current_lines:
                            event = parse_sse_event(current_lines)
                            current_lines = []

                            if "comment" in event and not event.get("event"):
                                ping_count += 1
                                print(f"[{timestamp()}] ping (keepalive)")
                            elif event.get("event") == "state":
                                state_events += 1
                                print_state_event(event)
                            elif event:
                                other_events += 1
                                print(f"[{timestamp()}] event={event.get('event', 'unknown')}: {event}")
                        continue

                    # Comment-only lines (no preceding event: line)
                    if line.startswith(":") and not current_lines:
                        ping_count += 1
                        print(f"[{timestamp()}] ping (keepalive)")
                        continue

                    current_lines.append(line)

    except KeyboardInterrupt:
        pass
    except httpx.ReadTimeout:
        print(f"\n[{timestamp()}] Connection timed out (expected after duration)")

    # Summary
    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print("EventSource Discovery Summary")
    print("=" * 60)
    print(f"  Duration:      {elapsed:.1f}s")
    print(f"  State events:  {state_events}")
    print(f"  Pings:         {ping_count}")
    print(f"  Other events:  {other_events}")

    total_events = state_events + ping_count + other_events
    if elapsed > 0:
        print(f"  Event rate:    {total_events / elapsed:.2f} events/sec")
    else:
        print(f"  Event rate:    N/A (0s elapsed)")

    print()

    if state_events > 0:
        print(f"--- PASS --- ({state_events} state event(s) received)")
    else:
        print("--- FAIL ---")
        print("  No state events received during the listening period.")
        print("  Troubleshooting:")
        print("    1. Try a longer --duration (e.g., --duration 120)")
        print("    2. Send yourself an email while the script is running")
        print("    3. Apply or remove a label on an email in Fastmail")
        print("    4. Check that MAILROOM_JMAP_TOKEN has EventSource permissions")
        if ping_count > 0:
            print(f"  Note: {ping_count} keepalive ping(s) were received, so the connection is working.")
            print("  The endpoint is reachable -- just no mailbox state changes occurred.")


if __name__ == "__main__":
    main()
