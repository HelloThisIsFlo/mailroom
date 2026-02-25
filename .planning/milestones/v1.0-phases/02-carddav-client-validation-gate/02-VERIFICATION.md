---
phase: 02-carddav-client-validation-gate
verified: 2026-02-24T00:00:00Z
status: human_needed
score: 11/11 automated must-haves verified
human_verification:
  - test: "Run human-tests/test_4_carddav_auth.py against live Fastmail and confirm PASS printed"
    expected: "Addressbook URL discovered, all 4 groups (Imbox, Feed, Paper Trail, Jail) listed with href and uid, PASS printed"
    why_human: "Live network call to carddav.fastmail.com with real credentials -- cannot verify programmatically"
  - test: "Run human-tests/test_5_carddav_contacts.py against live Fastmail and confirm PASS printed"
    expected: "Test contact created, found by search (1 result), upsert does not create duplicate (still 1 result), visual Fastmail confirmation, PASS printed"
    why_human: "Creates real contacts in Fastmail; duplicate prevention requires live round-trip to confirm search-before-create works"
  - test: "Run human-tests/test_6_carddav_groups.py against live Fastmail and confirm PASS printed"
    expected: "Contact added to group, membership verified by fetching group vCard, ETag conflict injected and retry succeeds, PASS printed"
    why_human: "Group membership and ETag conflict retry require live Fastmail to confirm KIND:group model and 412 handling work end-to-end"
---

# Phase 2: CardDAV Client (Validation Gate) Verification Report

**Phase Goal:** The service can search, create, and update contacts via CardDAV, and reliably assign contacts to Fastmail contact groups using the KIND:group model -- verified against live Fastmail before proceeding
**Verified:** 2026-02-24T00:00:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | CardDAV client authenticates with Fastmail using Basic auth (email + app password) | VERIFIED | `httpx.BasicAuth(username, password)` in constructor at carddav.py:66; `test_connect_auth_failure` covers 401 |
| 2 | CardDAV client discovers the default address book URL via PROPFIND chain (/.well-known/carddav) | VERIFIED | 3-step PROPFIND in `connect()` at carddav.py:86-138; discovery URL fixed to `/.well-known/carddav` in commit dacf59f |
| 3 | All configured contact groups are validated at startup -- missing groups raise ValueError | VERIFIED | `validate_groups()` at carddav.py:186-247 raises ValueError listing missing names; `test_validate_groups_missing_group_raises` passes |
| 4 | Config includes carddav_username as a required field for Phase 2 | VERIFIED | `carddav_username: str = ""` at config.py:22; `contact_groups` property at config.py:83-90 |
| 5 | Searching by email finds existing contacts matching any EMAIL property on the vCard | VERIFIED | `search_by_email()` at carddav.py:249-305 sends REPORT addressbook-query with case-insensitive prop-filter; 5 tests pass |
| 6 | Creating a contact produces a valid vCard 3.0 with FN, N, EMAIL, NOTE (Added by Mailroom on DATE), and UID | VERIFIED | `create_contact()` at carddav.py:307-360 builds vCard via vobject; `test_create_contact_sends_valid_vcard` asserts VERSION=3.0, FN, EMAIL, NOTE, UUID |
| 7 | Adding a contact to a group appends X-ADDRESSBOOKSERVER-MEMBER entry to the group vCard | VERIFIED | `add_to_group()` at carddav.py:362-434 uses vobject to add `x-addressbookserver-member`; `test_add_to_group_appends_member` verifies both old and new URNs in PUT body |
| 8 | Group update uses If-Match ETag for concurrency safety and retries on 412 | VERIFIED | carddav.py:413-428 sends If-Match header; retry loop at carddav.py:392-433; `test_add_to_group_retries_on_412` verifies exactly 2 PUTs; `test_add_to_group_raises_after_max_retries` passes |
| 9 | Upsert flow correctly orchestrates search-create/merge-group for both new and existing contacts | VERIFIED | `upsert_contact()` at carddav.py:436-528; 4 tests cover new contact, existing contact, no-overwrite, merge-cautious |
| 10 | Human test scripts exercise all CardDAV operations against live Fastmail | VERIFIED (structure only) | 3 scripts exist, parse cleanly, implement all operations; live pass confirmed by user per SUMMARY |
| 11 | Live Fastmail validation gate passed | NEEDS HUMAN | SUMMARY 02-03 reports PASS; cannot verify programmatically -- see human verification section |

**Score:** 10/11 automated truths verified; 1 requires human confirmation

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/mailroom/clients/carddav.py` | CardDAV client with connect(), validate_groups(), search_by_email(), create_contact(), add_to_group(), upsert_contact() | VERIFIED | 529 lines; all 6 methods present with docstrings; connection guard in `_require_connection()` |
| `src/mailroom/core/config.py` | carddav_username config field and contact_groups property | VERIFIED | `carddav_username: str = ""` at line 22; `contact_groups` property returns all 4 group names at lines 83-90 |
| `tests/test_carddav_client.py` | Unit tests for all operations (min 200 lines) | VERIFIED | 987 lines; 25 tests across 5 classes; all 25 PASS |
| `pyproject.toml` | vobject dependency | VERIFIED | `"vobject>=0.9.9"` confirmed in dependencies |
| `human-tests/test_4_carddav_auth.py` | CardDAV auth + discovery + group validation test (min 20 lines) | VERIFIED | 57 lines; syntactically valid; exercises connect() and validate_groups() |
| `human-tests/test_5_carddav_contacts.py` | Contact create, search, duplicate prevention test (min 40 lines) | VERIFIED | 124 lines; syntactically valid; 4 steps with PASS/FAIL |
| `human-tests/test_6_carddav_groups.py` | Group membership and ETag conflict test (min 50 lines) | VERIFIED | 191 lines; syntactically valid; deterministic ETag conflict test via monkey-patch |
| `human-tests/.env.example` | CardDAV credential placeholders | VERIFIED | MAILROOM_CARDDAV_USERNAME and MAILROOM_CARDDAV_PASSWORD added in commit 80d5d0c |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `carddav.py` constructor | `httpx.BasicAuth` | `httpx.BasicAuth(username, password)` | WIRED | carddav.py:66, imported at line 9 |
| `connect()` | `xml.etree.ElementTree` | `ET.fromstring(resp.content)` | WIRED | carddav.py:93, 106, 119; `import xml.etree.ElementTree as ET` at line 6 |
| `config.py` | `carddav_username` field | field declared, consumed by CardDAVClient constructor | WIRED | config.py:22; human tests feed `settings.carddav_username` to CardDAVClient constructor |
| `search_by_email()` | REPORT addressbook-query | ElementTree XML with prop-filter on EMAIL | WIRED | carddav.py:267-302; `test_search_by_email_sends_report_request` asserts method=REPORT, addressbook-query in body, EMAIL in body |
| `create_contact()` | PUT `{addressbook}/{uuid}.vcf` | vobject serialization with `If-None-Match: *` | WIRED | carddav.py:346-354; `test_create_contact_uses_if_none_match` asserts header present |
| `add_to_group()` | PUT group vCard | GET group, add MEMBER line, PUT with If-Match | WIRED | carddav.py:394-428; `test_add_to_group_uses_if_match` asserts If-Match == ETag from GET |
| `upsert_contact()` | search_by_email -> create_contact/merge -> add_to_group | orchestration method | WIRED | carddav.py:459-523; both branches call add_to_group at lines 464, 523 |
| `test_4_carddav_auth.py` | `CardDAVClient.connect() + validate_groups()` | direct method calls with live credentials | WIRED | test_4:31-43, client.connect() and client.validate_groups() called explicitly |
| `test_6_carddav_groups.py` | `input()` pause for ETag observation | `input("After editing, press Enter to continue: ")` | WIRED | test_6:114; additional deterministic test at lines 148-179 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CDAV-01 | 02-01, 02-03 | Service can authenticate with Fastmail CardDAV using Basic auth (app password) | SATISFIED | `httpx.BasicAuth` in constructor; 3-step PROPFIND discovery via /.well-known/carddav; test_connect_* tests pass |
| CDAV-02 | 02-02, 02-03 | Service can search contacts by email address to check for existing contacts | SATISFIED | `search_by_email()` sends REPORT addressbook-query with case-insensitive email filter; 5 unit tests pass |
| CDAV-03 | 02-02, 02-03 | Service can create a new contact vCard for a sender | SATISFIED | `create_contact()` produces valid vCard 3.0 (FN, N, EMAIL, NOTE, UID) with If-None-Match; 4 unit tests pass |
| CDAV-04 | 02-02, 02-03 | Service can add a contact to a contact group (Imbox, Feed, Paper Trail, Jail) | SATISFIED | `add_to_group()` appends X-ADDRESSBOOKSERVER-MEMBER with If-Match/412 retry; 5 unit tests pass |
| CDAV-05 | 02-02, 02-03 | Service handles existing contacts -- adds to group without creating duplicates | SATISFIED | `upsert_contact()` searches before creating; merge-cautious update fills only empty fields; 4 unit tests pass |

No orphaned requirements. All 5 CDAV requirements claimed across plans and verified.

### Anti-Patterns Found

No anti-patterns found. Scan of `src/mailroom/clients/carddav.py` and `tests/test_carddav_client.py` found:
- No TODO/FIXME/HACK/PLACEHOLDER comments
- No stub return values (return null / return {} / return [])
- No console.log-only implementations
- All 6 methods have substantive implementations with docstrings

One notable deviation documented in SUMMARY 02-03: a logging addition (`e41238b`) was reverted (`ec3063e`) per user preference to defer uniform logging to a later phase. The revert is clean -- no dead logging code remains.

### Human Verification Required

The SUMMARY for plan 02-03 states all 3 human test scripts were run against live Fastmail and returned PASS. The phase was marked complete by the user (checkpoint:human-verify approved). This verification report records that claim and flags it as requiring human confirmation since it cannot be re-verified programmatically.

#### 1. CardDAV Authentication and Discovery

**Test:** `cd human-tests && uv run python test_4_carddav_auth.py`
**Expected:** Prints the discovered addressbook URL, lists all 4 contact groups (Imbox, Feed, Paper Trail, Jail) with their hrefs and UIDs, prints `--- PASS ---`
**Why human:** Live network call to carddav.fastmail.com with real credentials. Verifies the /.well-known/carddav discovery fix (dacf59f) works against the live service and the KIND:group detection correctly identifies the 4 groups.

#### 2. Contact Create, Search, and Duplicate Prevention

**Test:** `cd human-tests && uv run python test_5_carddav_contacts.py`
**Expected:** Creates mailroom-test@example.com, finds it with search_by_email (exactly 1 result), upsert does not create a second copy (still 1 result after upsert), contact is visible in Fastmail web UI, prints `--- PASS ---`
**Why human:** Duplicate prevention (CDAV-05) depends on the live REPORT addressbook-query returning results -- cannot confirm the search actually works against Fastmail's CardDAV implementation without running it.

#### 3. Group Membership and ETag Conflict Handling

**Test:** `cd human-tests && uv run python test_6_carddav_groups.py`
**Expected:** Test contact created, added to first group (Imbox), membership verified by fetching group vCard and checking X-ADDRESSBOOKSERVER-MEMBER URN, deterministic 412 conflict injected and retry succeeds, prints `--- PASS ---`
**Why human:** Confirms the KIND:group model (CDAV-04) works with Fastmail -- specifically that adding X-ADDRESSBOOKSERVER-MEMBER to a group vCard actually places the contact in the group as seen in Fastmail's UI and API rules.

### Test Suite Results

```
62 passed in 0.37s (full suite, no regressions)
25 passed in 0.16s (test_carddav_client.py only)
ruff check src/ tests/ -- All checks passed!
```

All unit tests pass. No lint errors. The CardDAV client is fully tested with mocked httpx responses covering all operations and edge cases.

### Gaps Summary

No gaps. All automated checks pass. The phase goal is fully implemented:
- `CardDAVClient` is substantive (529 lines, 6 methods, all wired)
- Config additions are backward-compatible and correct
- 25 unit tests cover all operations including edge cases (auth failure, missing groups, no results, 412 retry, already-member, duplicate prevention, merge-cautious update)
- Human test scripts are substantive and follow the established pattern
- .env.example documents CardDAV credentials
- All 9 phase 2 commits verified in git history
- Discovery URL bug (/) fixed to (/.well-known/carddav) in commit dacf59f

The only remaining item is human confirmation that the 3 test scripts passed against live Fastmail. The SUMMARY records the user approved the checkpoint. If the user has already confirmed this in the GSD orchestration flow, the phase can be considered complete.

---

_Verified: 2026-02-24T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
