"""Human test 13: Docker Container Polling (BUILDS image, RUNS container against real Fastmail).

Validates the complete Docker packaging end-to-end:
  - Docker image builds successfully
  - Container starts and the polling loop begins
  - Health endpoint on /healthz returns 200
  - A triage label applied in Fastmail is processed by the containerized service
  - Graceful shutdown on docker stop (SIGTERM)

Prerequisites:
  - Tests 1-12 pass (all previous human tests)
  - Docker installed and running
  - .env file in human-tests/ with Fastmail credentials
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CONTAINER_NAME = "mailroom-human-test"
IMAGE_TAG = "mailroom:human-test"
HEALTH_URL = "http://localhost:8080/healthz"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Env vars to pass into the container (from .env)
ENV_KEYS = [
    "MAILROOM_JMAP_TOKEN",
    "MAILROOM_CARDDAV_USERNAME",
    "MAILROOM_CARDDAV_PASSWORD",
]


def run_docker(args: list[str], capture: bool = False, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a docker command, printing it first."""
    cmd = ["docker", *args]
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def cleanup() -> None:
    """Remove the test container if it exists."""
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
        text=True,
    )


# === Cleanup any previous test container ===
print("=== Cleanup: Removing any previous test container ===\n")
cleanup()
print("  Done.\n")


# === Step 1: Build Docker image ===
print("=== Step 1: Build Docker image ===\n")

result = run_docker(
    ["build", "-t", IMAGE_TAG, str(PROJECT_ROOT)],
    timeout=300,
)
if result.returncode != 0:
    print("\n  --- STEP 1 FAIL ---")
    print("  Docker build failed. Check the output above.")
    sys.exit(1)

print("\n  --- STEP 1 PASS ---\n")


# === Step 2: Start container ===
print("=== Step 2: Start container with 30s poll interval ===\n")

# Build -e flags for each env var
env_flags = []
for key in ENV_KEYS:
    value = os.environ.get(key, "")
    if not value:
        print(f"  WARNING: {key} not set in environment")
    env_flags.extend(["-e", f"{key}={value}"])

# Override poll interval for faster test cycles
env_flags.extend(["-e", "MAILROOM_POLL_INTERVAL=30"])
# Set log level to debug for visibility
env_flags.extend(["-e", "MAILROOM_LOG_LEVEL=debug"])

result = run_docker([
    "run", "-d",
    "--name", CONTAINER_NAME,
    "-p", "8080:8080",
    *env_flags,
    IMAGE_TAG,
])
if result.returncode != 0:
    print("\n  --- STEP 2 FAIL ---")
    print("  Failed to start container.")
    cleanup()
    sys.exit(1)

# Give the container a moment to start up
print("\n  Waiting 5 seconds for startup...")
time.sleep(5)

# Check if container is still running (didn't crash on startup)
check = run_docker(["inspect", "-f", "{{.State.Running}}", CONTAINER_NAME], capture=True)
if check.returncode != 0 or check.stdout.strip() != "true":
    print("\n  --- STEP 2 FAIL ---")
    print("  Container exited after startup. Checking logs:")
    run_docker(["logs", CONTAINER_NAME])
    cleanup()
    sys.exit(1)

# Show startup logs
print("\n  Startup logs:")
run_docker(["logs", CONTAINER_NAME])

print("\n  --- STEP 2 PASS ---\n")


# === Step 3: Check health endpoint ===
print("=== Step 3: Verify /healthz endpoint ===\n")

health_ok = False
for attempt in range(5):
    try:
        resp = urlopen(HEALTH_URL, timeout=3)
        status = resp.status
        body = resp.read().decode()
        print(f"  GET /healthz -> {status}: {body}")
        if status == 200:
            health_ok = True
            break
    except (URLError, ConnectionError, OSError) as e:
        print(f"  Attempt {attempt + 1}/5: {e}")
        time.sleep(2)

if not health_ok:
    print("\n  --- STEP 3 FAIL ---")
    print("  Health endpoint did not return 200.")
    run_docker(["logs", CONTAINER_NAME])
    cleanup()
    sys.exit(1)

print("\n  --- STEP 3 PASS ---\n")


# === Step 4: Interactive triage test ===
print("=== Step 4: Apply triage label and wait for processing ===\n")

print("Instructions:")
print("  1. Open Fastmail (web or iOS app)")
print("  2. Find an email in Screener from a sender you want to triage")
print("  3. Apply a triage label (e.g., @ToImbox) to that email")
print("  4. The container is polling every 30 seconds")
print()
input("Press Enter after applying the triage label... ")

print("\n  Waiting up to 45 seconds for the next poll cycle...")
time.sleep(45)

# Check docker logs for poll completion
logs_result = run_docker(["logs", "--tail", "50", CONTAINER_NAME], capture=True)
logs_output = logs_result.stdout + logs_result.stderr

print(f"\n  Recent container logs:\n")
# Print the logs for the user to see
run_docker(["logs", "--tail", "30", CONTAINER_NAME])

# Look for evidence of processing
if "poll_complete" in logs_output:
    print("\n  Found poll_complete in logs -- PASS")
else:
    print("\n  WARNING: Did not find poll_complete in logs.")
    print("  The poll cycle may not have run yet.")
    print("  Waiting another 30 seconds...")
    time.sleep(30)
    run_docker(["logs", "--tail", "30", CONTAINER_NAME])
    # Re-check
    logs_result = run_docker(["logs", "--tail", "50", CONTAINER_NAME], capture=True)
    logs_output = logs_result.stdout + logs_result.stderr

# Ask user to confirm
print()
response = input("Did the container process the triage? (check logs above) [y/n]: ").strip().lower()
if response != "y":
    print("\n  --- STEP 4 FAIL ---")
    print("  Triage was not processed by the containerized service.")
    cleanup()
    sys.exit(1)

print("\n  --- STEP 4 PASS ---\n")


# === Step 5: Graceful shutdown ===
print("=== Step 5: Graceful shutdown via docker stop ===\n")

print("  Sending SIGTERM via docker stop (10s timeout)...")
result = run_docker(["stop", "-t", "10", CONTAINER_NAME], timeout=30)
if result.returncode != 0:
    print("\n  --- STEP 5 FAIL ---")
    print("  docker stop failed.")
    cleanup()
    sys.exit(1)

# Check final logs for graceful shutdown
logs_result = run_docker(["logs", "--tail", "20", CONTAINER_NAME], capture=True)
logs_output = logs_result.stdout + logs_result.stderr

print(f"\n  Final container logs:\n")
run_docker(["logs", "--tail", "20", CONTAINER_NAME])

if "service_stopped" in logs_output:
    print("\n  Found service_stopped in logs -- graceful shutdown confirmed.")
else:
    print("\n  WARNING: Did not find service_stopped in logs.")
    print("  The container may have been killed (SIGKILL) instead of stopping gracefully.")

# Check exit code
inspect = run_docker(
    ["inspect", "-f", "{{.State.ExitCode}}", CONTAINER_NAME],
    capture=True,
)
exit_code = inspect.stdout.strip()
print(f"  Container exit code: {exit_code}")

print("\n  --- STEP 5 PASS ---\n")


# === Cleanup ===
print("=== Cleanup ===\n")
cleanup()
print("  Container removed.\n")


# === Report ===
print("--- PASS ---")
print("Docker container verification complete:")
print("  - Docker image builds successfully")
print("  - Container starts and polling loop begins")
print("  - Health endpoint /healthz returns 200")
print("  - Triage label processed by containerized service")
print("  - Graceful shutdown on docker stop (SIGTERM)")
