import subprocess
from fastapi import Depends, APIRouter
from auth import verify_api_key
import os
from models import (
    microvms,
    WORK_DIR,
)
import asyncio

router = APIRouter()


@router.post("/maintenance")
async def maintenance(_: str = Depends(verify_api_key)):
    """
    Background task that runs every 5 minutes to clean up orphaned resources.

    Cleans up:
    - TAP devices not in our tracking dict
    - Firecracker processes not in our tracking dict
    - VM directories without active VMs
    """
    try:
        print("🧹 Running orphan cleanup...")

        # Get list of tracked TAP devices and IPs
        tracked_taps = set()
        tracked_pids = set()
        tracked_ips = set()
        for user_id, vm in microvms.items():
            tracked_taps.add(vm["tap_device"])  # Use actual tap_device name!
            tracked_pids.add(vm["process"].pid)
            tracked_ips.add(vm["ip"])

        # Find and delete orphaned routes (must be done before TAP deletion)
        try:
            result = subprocess.run(
                ["ip", "route", "show"], capture_output=True, text=True, timeout=5
            )

            for line in result.stdout.split("\n"):
                # Look for routes like: 10.0.1.100/32 dev tap-xxxxx
                if "/32 dev tap-" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        route_ip = parts[0]  # e.g., 10.0.1.100/32
                        route_ip_clean = route_ip.replace("/32", "")

                        if route_ip_clean not in tracked_ips:
                            print(f"  Found orphaned route: {route_ip}")
                            try:
                                subprocess.run(
                                    ["sudo", "ip", "route", "del", route_ip],
                                    timeout=5,
                                    check=False,
                                )
                                print(f"  ✓ Deleted orphaned route: {route_ip}")
                            except Exception as e:
                                print(f"  ⚠️ Failed to delete route {route_ip}: {e}")

        except Exception as e:
            print(f"  ⚠️ Route cleanup error: {e}")

        # Find and delete orphaned TAP devices
        try:
            result = subprocess.run(
                ["ip", "link", "show"], capture_output=True, text=True, timeout=5
            )

            for line in result.stdout.split("\n"):
                if "tap-" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        tap_name = parts[1].rstrip(":")
                        if tap_name.startswith("tap-") and tap_name not in tracked_taps:
                            print(f"  Found orphaned TAP device: {tap_name}")
                            try:
                                subprocess.run(
                                    ["sudo", "ip", "link", "delete", tap_name],
                                    timeout=5,
                                    check=False,
                                )
                                print(f"  ✓ Deleted orphaned TAP device: {tap_name}")
                            except Exception as e:
                                print(f"  ⚠️ Failed to delete {tap_name}: {e}")

        except Exception as e:
            print(f"  ⚠️ TAP cleanup error: {e}")

        # Find and kill orphaned Firecracker processes
        try:
            result = subprocess.run(
                ["pgrep", "-f", "/usr/local/bin/firecracker"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            for pid_str in result.stdout.strip().split("\n"):
                if pid_str:
                    try:
                        pid = int(pid_str)
                        if pid not in tracked_pids:
                            print(f"  Found orphaned Firecracker process: PID {pid}")
                            subprocess.run(
                                ["sudo", "kill", "-9", str(pid)],
                                timeout=5,
                                check=False,
                            )
                            print(f"  ✓ Killed orphaned process: PID {pid}")
                    except ValueError:
                        pass
                    except Exception as e:
                        print(f"  ⚠️ Failed to kill PID {pid_str}: {e}")

        except subprocess.CalledProcessError:
            pass  # No firecracker processes found
        except Exception as e:
            print(f"  ⚠️ Process cleanup error: {e}")

        # Clean up orphaned VM directories
        try:
            tracked_users = set(microvms.keys())

            if os.path.exists(WORK_DIR):
                for user_dir in os.listdir(WORK_DIR):
                    if user_dir not in tracked_users:
                        orphaned_dir = os.path.join(WORK_DIR, user_dir)
                        print(f"  Found orphaned VM directory: {orphaned_dir}")
                        try:
                            import shutil

                            shutil.rmtree(orphaned_dir)
                            print(f"  ✓ Deleted orphaned directory: {orphaned_dir}")
                        except Exception as e:
                            print(f"  ⚠️ Failed to delete {orphaned_dir}: {e}")

        except Exception as e:
            print(f"  ⚠️ Directory cleanup error: {e}")

        print("✅ Orphan cleanup complete")
        return {"status": "success", "message": "Orphan cleanup completed"}

    except Exception as e:
        print(f"❌ Cleanup task error: {e}")
        return {"status": "error", "message": str(e)}
