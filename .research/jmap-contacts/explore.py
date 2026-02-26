"""
Explore Fastmail JMAP Contacts API — find contact groups and their IDs.

Usage:
    python explore_jmap_contacts.py

Requires:
    - MAILROOM_JMAP_TOKEN in .env
    - pip install python-dotenv requests
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["MAILROOM_JMAP_TOKEN"]
API_URL = "https://api.fastmail.com/jmap/api/"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

USING = [
    "urn:ietf:params:jmap:core",
    "urn:ietf:params:jmap:contacts",
]


def jmap_call(method_calls: list) -> dict:
    """Make a JMAP API call and return the parsed response."""
    payload = {"using": USING, "methodCalls": method_calls}
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def get_account_id() -> str:
    """Fetch account ID from session."""
    resp = requests.get(
        "https://api.fastmail.com/jmap/session",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    resp.raise_for_status()
    session = resp.json()
    return session["primaryAccounts"]["urn:ietf:params:jmap:contacts"]


def main():
    account_id = get_account_id()
    print(f"Account ID: {account_id}\n")

    # ──────────────────────────────────────────────
    # 1. Try querying for contact groups via filter
    # ──────────────────────────────────────────────
    print("=" * 60)
    print("1. Querying ContactCard with filter kind=group")
    print("=" * 60)

    try:
        result = jmap_call([
            ["ContactCard/query", {
                "accountId": account_id,
                "filter": {"kind": "group"},
            }, "q0"],
            ["ContactCard/get", {
                "accountId": account_id,
                "#ids": {
                    "resultOf": "q0",
                    "name": "ContactCard/query",
                    "path": "/ids",
                },
            }, "g0"],
        ])

        for method_name, data, tag in result["methodResponses"]:
            if method_name == "error":
                print(f"  Error ({tag}): {data}")
            elif method_name == "ContactCard/query":
                print(f"  Found {len(data.get('ids', []))} group(s)")
            elif method_name == "ContactCard/get":
                cards = data.get("list", [])
                if not cards:
                    print("  No groups returned.")
                for card in cards:
                    print(f"\n  Group: {card.get('name', card.get('fullName', '???'))}")
                    print(f"    JMAP ID : {card['id']}")
                    print(f"    UID     : {card.get('uid', 'N/A')}")
                    members = card.get("members", {})
                    if members:
                        print(f"    Members : {len(members)} contact(s)")
                        for uid in list(members.keys())[:5]:
                            print(f"      - {uid}")
                        if len(members) > 5:
                            print(f"      ... and {len(members) - 5} more")
                    else:
                        print("    Members : (none or not returned)")
    except Exception as e:
        print(f"  Failed: {e}")

    # ──────────────────────────────────────────────
    # 2. Fallback: fetch ALL ContactCards, filter client-side
    #    (in case the kind filter isn't supported)
    # ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("2. Fetching all ContactCards (fallback — find groups client-side)")
    print("=" * 60)

    try:
        result = jmap_call([
            ["ContactCard/get", {
                "accountId": account_id,
            }, "all"],
        ])

        for method_name, data, tag in result["methodResponses"]:
            if method_name == "error":
                print(f"  Error: {data}")
                continue

            cards = data.get("list", [])
            print(f"  Total ContactCards: {len(cards)}")

            groups = [c for c in cards if c.get("kind") == "group"]
            print(f"  Groups (kind=group): {len(groups)}")

            for g in groups:
                name = g.get("name", g.get("fullName", "???"))
                print(f"\n  Group: {name}")
                print(f"    JMAP ID : {g['id']}")
                print(f"    UID     : {g.get('uid', 'N/A')}")
                members = g.get("members", {})
                print(f"    Members : {len(members)} contact(s)")

            # Also show what 'kind' values exist
            kinds = {}
            for c in cards:
                k = c.get("kind", "(no kind)")
                kinds[k] = kinds.get(k, 0) + 1
            print(f"\n  Kind distribution: {kinds}")

            # Show first card's full structure for debugging
            if cards:
                print(f"\n  Sample card keys: {list(cards[0].keys())}")

    except Exception as e:
        print(f"  Failed: {e}")

    # ──────────────────────────────────────────────
    # 3. Try legacy Fastmail-specific method (ContactGroup/get)
    #    This may or may not work — worth testing
    # ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("3. Trying legacy ContactGroup/get (Fastmail proprietary)")
    print("=" * 60)

    try:
        result = jmap_call([
            ["ContactGroup/get", {
                "accountId": account_id,
            }, "lg"],
        ])

        for method_name, data, tag in result["methodResponses"]:
            if method_name == "error":
                print(f"  Error: {data}")
            else:
                groups = data.get("list", [])
                print(f"  Found {len(groups)} group(s)")
                for g in groups:
                    print(f"\n  Group: {g.get('name', '???')}")
                    print(f"    ID      : {g.get('id', 'N/A')}")
                    print(f"    Full obj: {json.dumps(g, indent=6)}")
    except Exception as e:
        print(f"  Failed: {e}")

    # ──────────────────────────────────────────────
    # 4. List AddressBooks
    # ──────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("4. Listing AddressBooks")
    print("=" * 60)

    try:
        result = jmap_call([
            ["AddressBook/get", {
                "accountId": account_id,
            }, "ab"],
        ])

        for method_name, data, tag in result["methodResponses"]:
            if method_name == "error":
                print(f"  Error: {data}")
            else:
                books = data.get("list", [])
                print(f"  Found {len(books)} address book(s)")
                for b in books:
                    print(f"\n  AddressBook: {b.get('name', '???')}")
                    print(f"    ID        : {b['id']}")
                    print(f"    isDefault : {b.get('isDefault', 'N/A')}")
    except Exception as e:
        print(f"  Failed: {e}")


if __name__ == "__main__":
    main()