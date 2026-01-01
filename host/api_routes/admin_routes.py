import asyncio
from connectrpc.client import ConnectClient
from connectrpc.method import MethodInfo, IdempotencyLevel
import process_pb2
import filesystem_pb2
from fastapi import HTTPException, Depends, APIRouter
import subprocess
import os
import signal
import time
from auth import verify_api_key
from models import (
    microvms,
    CreateMicroVMRequest,
    TaskRequest,
    KillMicroVMRequest,
    FIRECRACKER_BIN,
    KERNEL_PATH,
    WORK_DIR,
    ROOTFS_IMAGES,
    next_ip,
    START_METHOD,
)

router = APIRouter()


@router.get("/status")
async def get_status(_: str = Depends(verify_api_key)):
    """Get host status (for monitoring)"""
    current_time = time.time()

    return {
        "active_microvms": len(microvms),
        "available_runtimes": list(ROOTFS_IMAGES.keys()),
        "microvms": {
            user_id: {
                "ip": vm["ip"],
                "runtime": vm["runtime"],
                "pid": vm["process"].pid,
                "alive": vm["process"].poll() is None,
                "created_at": vm.get("created_at"),
                "age_seconds": (
                    int(current_time - vm.get("created_at", current_time))
                    if vm.get("created_at")
                    else None
                ),
            }
            for user_id, vm in microvms.items()
        },
    }


@router.get("/list_processes")
async def list_processes(user_id: str, _: str = Depends(verify_api_key)):
    """List all running processes in the microVM"""
    if user_id not in microvms:
        raise HTTPException(404, f"No microVM for {user_id}")

    vm = microvms[user_id]
    vm_ip = vm["ip"]

    rpc_client = ConnectClient(f"http://{vm_ip}:49983")

    request = process_pb2.ListRequest()

    LIST_METHOD = MethodInfo(
        name="List",
        service_name="process.Process",
        input=process_pb2.ListRequest,
        output=process_pb2.ListResponse,
        idempotency_level=IdempotencyLevel.NO_SIDE_EFFECTS,
    )

    response = await rpc_client.execute_unary(request=request, method=LIST_METHOD)

    processes = []
    for proc_info in response.processes:
        processes.append(
            {
                "pid": proc_info.pid,
                "cmd": proc_info.config.cmd,
                "args": list(proc_info.config.args),
                "cwd": (
                    proc_info.config.cwd if proc_info.config.HasField("cwd") else None
                ),
            }
        )

    return {"processes": processes}


@router.post("/kill_microvm")
async def kill_microvm(
    request: KillMicroVMRequest, force: bool = False, _: str = Depends(verify_api_key)
):
    user_id = request.user_id
    vm_dir = f"{WORK_DIR}/{user_id}"

    if user_id not in microvms:
        if not force:
            raise HTTPException(
                status_code=404,
                detail=f"No microVM found for user {user_id}. Use force=true to cleanup anyway.",
            )

        # Force mode: cleanup even without tracking
        print(f"🔪 Force killing microVM for user {user_id}")

        # Kill any firecracker process for this user
        try:
            result = subprocess.run(
                ["pgrep", "-f", f"firecracker.*{user_id}"],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                for pid in result.stdout.strip().split("\n"):
                    subprocess.run(["sudo", "kill", "-9", pid], check=False)
                    print(f"  ✓ Killed process {pid}")
        except Exception as e:
            print(f"  ⚠️ Error killing processes: {e}")

        # Find and delete TAP device
        try:
            result = subprocess.run(
                ["ip", "link", "show"], capture_output=True, text=True
            )
            for line in result.stdout.split("\n"):
                if "tap-" in line and user_id[:11] in line:
                    tap_name = line.split(":")[1].strip().split("@")[0]
                    subprocess.run(
                        ["sudo", "ip", "link", "delete", tap_name], check=False
                    )
                    print(f"  ✓ Deleted TAP device {tap_name}")
        except Exception as e:
            print(f"  ⚠️ Error cleaning TAP: {e}")

        # Disconnect any NBD devices (try all, one might be ours)
        for i in range(16):
            dev = f"/dev/nbd{i}"
            subprocess.run(
                ["sudo", "qemu-nbd", "-d", dev], capture_output=True, check=False
            )

        # Delete VM directory
        if os.path.exists(vm_dir):
            import shutil

            try:
                shutil.rmtree(vm_dir)
                print(f"  ✓ Deleted VM directory {vm_dir}")
            except:
                subprocess.run(["sudo", "rm", "-rf", vm_dir], check=False)
                print(f"  ✓ Force deleted VM directory")

        return {"status": "force_killed", "user_id": user_id}

    vm = microvms[user_id]
    proc = vm["process"]
    tap_device = vm["tap_device"]
    nbd_device = vm.get("nbd_device")

    print(f"🔪 Killing microVM for user {user_id} (PID: {proc.pid})")

    # Step 1: Kill Firecracker process with retries
    for attempt in range(3):
        try:
            if proc.poll() is None:  # Process still running
                print(f"  Attempt {attempt+1}: Sending SIGKILL to PID {proc.pid}")
                proc.send_signal(signal.SIGKILL)
                proc.wait(timeout=3)
                print(f"  ✓ Process {proc.pid} terminated")
            break
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ Process {proc.pid} didn't die, retrying...")
            if attempt == 2:
                print(f"  ⚠️ WARNING: Process {proc.pid} may be stuck")
        except Exception as e:
            print(f"  ⚠️ Error killing process: {e}")

    # Step 2: Force kill any remaining process by PID
    try:
        subprocess.run(
            ["sudo", "kill", "-9", str(proc.pid)],
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except:
        pass

    # Step 3: Delete route first (must be done before TAP deletion)
    vm_ip = vm["ip"]
    try:
        subprocess.run(
            ["sudo", "ip", "route", "del", f"{vm_ip}/32"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        print(f"  ✓ Deleted route to {vm_ip}/32")
    except Exception as e:
        print(f"  ⚠️ Route delete error (may not exist): {e}")

    # Step 4: Delete TAP network device with retries
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["sudo", "ip", "link", "delete", tap_device],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                print(f"  ✓ Deleted TAP device {tap_device}")
                break
            elif "Cannot find device" in result.stderr:
                print(f"  ✓ TAP device {tap_device} already gone")
                break
            else:
                print(
                    f"  ⚠️ TAP delete attempt {attempt+1} failed: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            print(f"  ⚠️ TAP delete timeout on attempt {attempt+1}")
        except Exception as e:
            print(f"  ⚠️ TAP delete error: {e}")

        if attempt < 2:
            await asyncio.sleep(0.5)

    # Step 5: Disconnect NBD device
    if nbd_device:
        try:
            subprocess.run(
                ["sudo", "qemu-nbd", "-d", nbd_device],
                capture_output=True,
                timeout=5,
                check=False,
            )
            print(f"  ✓ Disconnected NBD device {nbd_device}")
            # Wait for lock file to be fully released
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  ⚠️ NBD disconnect error: {e}")

    # Step 6: Clean up VM directory with retries
    for attempt in range(3):
        try:
            import shutil

            if os.path.exists(vm_dir):
                shutil.rmtree(vm_dir)
                print(f"  ✓ Deleted VM directory {vm_dir}")
            break
        except Exception as e:
            print(f"  ⚠️ Directory cleanup attempt {attempt+1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(0.5)
            elif attempt == 2:
                # Last resort: force remove
                try:
                    subprocess.run(
                        ["sudo", "rm", "-rf", vm_dir], timeout=5, check=False
                    )
                    print(f"  ✓ Force deleted VM directory")
                except:
                    print(f"  ❌ Could not delete {vm_dir}, manual cleanup required")

    # Step 7: Remove from tracking
    del microvms[user_id]

    print(f"✅ Cleaned up microVM for user {user_id}")

    return {"status": "killed", "user_id": user_id}
