import asyncio
from connectrpc.client import ConnectClient
from connectrpc.method import MethodInfo, IdempotencyLevel
import filesystem_pb2
from fastapi import HTTPException, Request, Depends, APIRouter
from fastapi.responses import StreamingResponse, Response
from typing import Dict
from config import SKIP_DIRS, SKIP_FILES
import subprocess
import httpx
import json
import os
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


@router.post("/create_microvm")
async def create_microvm(
    request: CreateMicroVMRequest, _: str = Depends(verify_api_key)
):
    """
    Create a new Firecracker microVM for this user.

    Args:
        user_id: User identifier
        runtime: Runtime environment ("python", "node", "python-data-science")
        env_vars: Environment variables to inject (API keys, etc.)

    Returns:
        {"status": "created", "vm_ip": "10.0.1.100"}
    """
    global next_ip

    user_id = request.user_id
    runtime = request.runtime
    env_vars = request.env_vars

    start_time = time.time()
    print(
        f"[DEBUG] [{time.time()-start_time:.3f}s] create_microvm called for user_id={user_id}, runtime={runtime}"
    )

    if user_id in microvms:
        print(
            f"[DEBUG] [{time.time()-start_time:.3f}s] microVM already exists for {user_id}"
        )
        return {"status": "already_exists", "vm_ip": microvms[user_id]["ip"]}

    print(
        f"🚀 [{time.time()-start_time:.3f}s] Creating microVM for user {user_id} with runtime: {runtime}"
    )

    # Validate runtime and get rootfs path
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Validating runtime {runtime}")
    if runtime not in ROOTFS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown runtime: {runtime}. Available: {list(ROOTFS_IMAGES.keys())}",
        )

    rootfs_path = ROOTFS_IMAGES[runtime]
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Using rootfs: {rootfs_path}")

    # Allocate IP
    vm_ip = f"10.0.1.{next_ip}"
    vm_ip_last_octet = next_ip
    next_ip += 1
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Allocated IP {vm_ip}")

    # Create short TAP device name (max 15 chars: "tap-" + 11 chars)
    # Use hash of user_id to create unique but short name
    import hashlib

    tap_suffix = hashlib.md5(user_id.encode()).hexdigest()[:11]
    tap_name = f"tap-{tap_suffix}"
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] TAP device: {tap_name}")

    # Create working directory for this microVM
    vm_dir = f"{WORK_DIR}/{user_id}"
    os.makedirs(vm_dir, exist_ok=True)
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Created VM dir {vm_dir}")

    # Create qcow2 overlay backed by base image (instant copy-on-write)
    user_qcow2 = f"{vm_dir}/rootfs.qcow2"
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Creating qcow2 overlay")

    qcow2_result = subprocess.run(
        [
            "qemu-img",
            "create",
            "-f",
            "qcow2",
            "-b",
            rootfs_path,
            "-F",
            "raw",
            user_qcow2,
        ],
        capture_output=True,
        text=True,
    )
    if qcow2_result.returncode != 0:
        raise HTTPException(
            status_code=500, detail=f"Failed to create qcow2: {qcow2_result.stderr}"
        )
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] qcow2 created")

    # Find available NBD device
    nbd_device = None
    for i in range(32):  ##########corresponds to max nbd in .service
        dev = f"/dev/nbd{i}"
        check = subprocess.run(
            ["sudo", "blockdev", "--getsize64", dev], capture_output=True
        )
        if check.returncode != 0 or check.stdout.strip() == b"0":
            nbd_device = dev
            break

    if not nbd_device:
        raise HTTPException(status_code=500, detail="No free NBD devices available")

    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Using NBD device {nbd_device}")

    # Connect qcow2 to NBD device
    nbd_result = subprocess.run(
        ["sudo", "qemu-nbd", "-c", nbd_device, user_qcow2],
        capture_output=True,
        text=True,
    )
    if nbd_result.returncode != 0:
        raise HTTPException(
            status_code=500, detail=f"Failed to connect NBD: {nbd_result.stderr}"
        )
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] NBD connected")

    user_rootfs = nbd_device

    # Clean up any existing socket files
    socket_path = f"{vm_dir}/firecracker.sock"
    if os.path.exists(socket_path):
        os.remove(socket_path)
        print(f"[DEBUG] [{time.time()-start_time:.3f}s] Removed old socket file")

    # Create Firecracker config
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Creating Firecracker config")
    config = {
        "boot-source": {
            "kernel_image_path": KERNEL_PATH,
            "boot_args": f"console=ttyS0 reboot=k panic=1 root=/dev/vda rw init=/sbin/init random.trust_cpu=on ip={vm_ip}::10.0.1.1:255.255.255.0:vm:eth0:off:{tap_name}",
        },
        "drives": [
            {
                "drive_id": "rootfs",
                "path_on_host": user_rootfs,
                "is_root_device": True,
                "is_read_only": False,
            }
        ],
        "machine-config": {
            "vcpu_count": 2,
            "mem_size_mib": 2048 if runtime == "claude-agent" else 1024,
        },
        "network-interfaces": [
            {
                "iface_id": "eth0",
                "guest_mac": f"AA:FC:00:00:00:{vm_ip_last_octet:02x}",
                "host_dev_name": tap_name,
            }
        ],
    }

    config_path = f"{vm_dir}/config.json"
    with open(config_path, "w") as f:
        json.dump(config, f)
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Wrote config to {config_path}")

    # Create TAP device for networking (async to avoid blocking)
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Starting TAP device creation")
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo", "ip", "tuntap", "add", tap_name, "mode", "tap"
        )
        await proc.wait()
        print(f"[DEBUG] [{time.time()-start_time:.3f}s] TAP device created")

        proc = await asyncio.create_subprocess_exec(
            "sudo", "ip", "addr", "add", "10.0.1.1/32", "dev", tap_name
        )
        await proc.wait()
        print(f"[DEBUG] [{time.time()-start_time:.3f}s] TAP IP configured as /32")

        proc = await asyncio.create_subprocess_exec(
            "sudo", "ip", "link", "set", tap_name, "up"
        )
        await proc.wait()
        print(f"[DEBUG] [{time.time()-start_time:.3f}s] TAP link up")

        proc = await asyncio.create_subprocess_exec(
            "sudo", "ip", "route", "add", f"{vm_ip}/32", "dev", tap_name
        )
        await proc.wait()
        print(f"[DEBUG] [{time.time()-start_time:.3f}s] Route to {vm_ip}/32 added")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Network setup failed: {e}")

    # Start Firecracker process
    print(f"[DEBUG] [{time.time()-start_time:.3f}s] Preparing to start Firecracker")
    socket_path = f"{vm_dir}/firecracker.sock"
    log_path = f"{vm_dir}/firecracker.log"
    print(
        f"[DEBUG] [{time.time()-start_time:.3f}s] Socket: {socket_path}, Log: {log_path}"
    )

    try:
        print(f"[DEBUG] [{time.time()-start_time:.3f}s] Opening log file {log_path}")
        log_file = open(log_path, "w")
        print(
            f"[DEBUG] [{time.time()-start_time:.3f}s] Log file opened, starting Popen"
        )
        proc = subprocess.Popen(
            [FIRECRACKER_BIN, "--api-sock", socket_path, "--config-file", config_path],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        print(
            f"[DEBUG] [{time.time()-start_time:.3f}s] Popen returned, PID: {proc.pid}"
        )

        print(
            f"✅ Started Firecracker for user {user_id} (PID: {proc.pid}), logs: {log_path}"
        )

        # Store microVM info
        microvms[user_id] = {
            "process": proc,
            "ip": vm_ip,
            "runtime": runtime,
            "socket": socket_path,
            "tap_device": tap_name,
            "nbd_device": nbd_device,  # NBD device for qcow2 overlay
            "running_process_pid": None,  # REPL kernel PID
            "background_process_pid": None,  # Background server PID (only one)
            "created_at": time.time(),  # Track creation timestamp
        }

        # Wait for envd to start inside microVM (usually 200-500ms)
        await wait_for_envd(vm_ip)

        # Always initialize envd
        await init_envd(vm_ip, env_vars)

        await wait_for_fastapi(vm_ip)

        return {"status": "created", "vm_ip": vm_ip, "pid": proc.pid}

    except Exception as e:
        # Cleanup on failure
        if proc:
            proc.kill()
        raise HTTPException(status_code=500, detail=f"Failed to start Firecracker: {e}")


async def wait_for_envd(vm_ip: str, timeout: int = 30):
    """
    Wait for envd to start inside the microVM.

    envd listens on port 49983. Check /health endpoint with fast retries.
    Retry w/ 5ms delays.
    """
    print(f"⏳ Waiting for envd to start at {vm_ip}:49983...", flush=True)

    max_attempts = timeout * 200
    for i in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://{vm_ip}:49983/health", timeout=2.0)
                if response.status_code == 204 or response.status_code == 200:
                    print(
                        f"✅ envd is ready at {vm_ip}:49983 (attempt {i+1}/{max_attempts})",
                        flush=True,
                    )
                    return
        except Exception as e:
            if i % 200 == 0 and i > 0:
                print(f"   Still waiting... attempt {i+1}/{max_attempts}", flush=True)
            pass

        await asyncio.sleep(0.005)

    raise HTTPException(
        status_code=500, detail=f"envd did not start within {timeout} seconds"
    )


async def init_envd(vm_ip: str, env_vars: Dict[str, str] = {}):
    """
    Initialize envd with environment variables and timestamp.

    This is how we inject API keys, etc. into the microVM.
    """
    try:
        async with httpx.AsyncClient() as client:
            payload = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            if env_vars:
                payload["envVars"] = env_vars

            response = await client.post(
                f"http://{vm_ip}:49983/init", json=payload, timeout=5.0
            )
            if response.status_code != 200 and response.status_code != 204:
                print(f"⚠️ Failed to initialize envd: {response.text}")
    except Exception as e:
        print(f"⚠️ Failed to initialize envd: {e}")


async def wait_for_fastapi(vm_ip: str, timeout: int = 60):
    """
    Wait for FastAPI wrapper to be fully ready inside the microVM.

    FastAPI listens on port 49999.
    """
    print(
        f"⏳ [HOST] Waiting for FastAPI to start at {vm_ip}:49999...",
        flush=True,
    )

    max_attempts = timeout * 10
    for i in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://{vm_ip}:49999/health", timeout=2.0)
                if response.status_code == 200:

                    health_data = response.json()
                    agent_ready = health_data.get("agent") == "ready"

                    if agent_ready:
                        backend = "Claude Agent"
                        print(
                            f"✅ [HOST] FastAPI and {backend} are ready at {vm_ip}:49999 (attempt {i+1}/{max_attempts})",
                            flush=True,
                        )
                        return
                    else:
                        # FastAPI is up but backend not ready yet
                        if i % 100 == 0 and i > 0:
                            print(
                                f"   [HOST] FastAPI up, waiting for backend... attempt {i+1}/{max_attempts}",
                                flush=True,
                            )
        except Exception as e:
            if i % 100 == 0 and i > 0:
                print(
                    f"   [HOST] Still waiting for FastAPI... attempt {i+1}/{max_attempts}, last error: {type(e).__name__}",
                    flush=True,
                )

        await asyncio.sleep(0.1)

    print(
        f"❌ [HOST] FastAPI did not start within {timeout} seconds after {max_attempts} attempts",
        flush=True,
    )
    raise HTTPException(
        status_code=500, detail=f"FastAPI did not start within {timeout} seconds"
    )


@router.post("/claude_in_the_box")
async def claude_in_the_box(request: TaskRequest, _: str = Depends(verify_api_key)):
    """
    Send task to claude agent in microvm

    Streams output back to caller in real-time.
    """
    user_id = request.user_id
    task = request.task
    context = request.context
    files = request.files
    filenames = list(files.keys())  # Extract filenames for claude agent

    # Check if microVM exists
    if user_id not in microvms:
        raise HTTPException(
            status_code=404, detail=f"No microVM found for user {user_id}"
        )

    vm = microvms[user_id]
    vm_ip = vm["ip"]
    runtime = vm["runtime"]

    print(f"▶️ Starting {runtime} code for user {user_id} on {vm_ip}")

    if files:
        async with httpx.AsyncClient() as http_client:
            for filename, content in files.items():
                try:
                    # Decode content properly
                    if isinstance(content, str):
                        # String could be base64 (from bash) or latin1 (from API)
                        try:
                            import base64

                            file_content = base64.b64decode(content)
                        except:
                            # Not base64, assume latin1 encoding from API
                            file_content = content.encode("latin1")
                    else:
                        file_content = content

                    await http_client.post(
                        f"http://{vm_ip}:49983/files",
                        params={"path": f"/workspace/{filename}"},
                        files={"file": file_content},
                    )
                    print(f"📤 Uploaded {filename} to microVM")
                except Exception as e:
                    print(f"⚠️ Failed to upload {filename}: {e}")

    # =========================================================================
    # Claude mode run in persisten sesion
    # =========================================================================

    print(f"🔧 Sending {runtime} code to FastAPI at {vm_ip}:49999")

    # Stream response from Claude FastAPI
    async def stream_from_claude_fastapi():
        try:
            async with httpx.AsyncClient(timeout=1800.0) as http_client:
                async with http_client.stream(
                    "POST",
                    f"http://{vm_ip}:49999/execute_task",
                    json={"task": task, "context": context, "files": filenames},
                ) as response:
                    # Check for errors
                    if response.status_code != 200:
                        error_msg = await response.aread()
                        # FastAPI returns {"detail": "error message"}, extract just the detail
                        try:
                            error_data = json.loads(error_msg)
                            error_detail = error_data.get("detail", error_msg.decode())
                        except:
                            error_detail = error_msg.decode()
                        raise HTTPException(500, error_detail)

                    # Stream output as bytes
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk

        except httpx.TimeoutException:
            raise HTTPException(500, "Request timed out after 1800 seconds")
        except httpx.ConnectError:
            raise HTTPException(
                500, f"Cannot connect to Claude FastAPI at {vm_ip}:49999"
            )
        except Exception as e:
            raise HTTPException(
                500, f"Error communicating with Claude FastAPI: {type(e).__name__}"
            )

    return StreamingResponse(stream_from_claude_fastapi(), media_type="text/plain")


@router.get(
    "/list_workspace_files",
)
async def list_workspace_files(user_id: str, _: str = Depends(verify_api_key)):
    """
    List all files in /workspace directory inside the microVM using filesystem gRPC API.

    Args:
        user_id: User identifier

    Returns:
        List of file paths relative to /workspace
    """
    if user_id not in microvms:
        raise HTTPException(404, f"No microVM for {user_id}")

    vm = microvms[user_id]
    vm_ip = vm["ip"]

    rpc_client = ConnectClient(f"http://{vm_ip}:49983")

    LIST_DIR_METHOD = MethodInfo(
        name="ListDir",
        service_name="filesystem.Filesystem",
        input=filesystem_pb2.ListDirRequest,
        output=filesystem_pb2.ListDirResponse,
        idempotency_level=IdempotencyLevel.NO_SIDE_EFFECTS,
    )

    list_request = filesystem_pb2.ListDirRequest(
        path="/workspace",
        depth=10,
    )

    try:
        response = await rpc_client.execute_unary(
            request=list_request, method=LIST_DIR_METHOD
        )

        files = []
        for entry in response.entries:
            if entry.type == filesystem_pb2.FileType.FILE_TYPE_FILE:
                filename = entry.path.replace("/workspace/", "", 1)

                # Skip dependency/cache directories (not user output)
                # Check if ANY skip pattern appears in the path (handles subfolders)
                skip_dirs = SKIP_DIRS
                if any(
                    f"/{d}" in f"/{filename}" or filename.startswith(d)
                    for d in skip_dirs
                ):
                    continue

                # Skip lock files and intermediate artifacts
                skip_files = SKIP_FILES
                if filename in skip_files:
                    continue

                files.append(filename)

        return {"files": files}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list workspace files: {str(e)}"
        )


@router.get("/download_file")
async def download_file(user_id: str, filename: str, _: str = Depends(verify_api_key)):
    if user_id not in microvms:
        raise HTTPException(
            status_code=404, detail=f"No microVM found for user {user_id}"
        )

    vm = microvms[user_id]
    vm_ip = vm["ip"]

    # Validate filename to prevent path traversal attacks
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(
            status_code=400, detail="Invalid filename: path traversal detected"
        )

    # Ensure normalized path stays within /workspace
    full_path = os.path.normpath(f"/workspace/{filename}")
    if not full_path.startswith("/workspace/"):
        raise HTTPException(
            status_code=400, detail="Invalid filename: must be within /workspace"
        )

    print(f"📥 Downloading file {filename} from microVM {user_id} ({vm_ip})")

    async with httpx.AsyncClient() as http_client:
        try:
            response = await http_client.get(
                f"http://{vm_ip}:49983/files", params={"path": full_path}
            )

            if response.status_code == 200:
                print(f"◉ Downloaded {filename} ({len(response.content)} bytes)")
                return Response(
                    content=response.content, media_type="application/octet-stream"
                )
            else:
                raise HTTPException(
                    status_code=404, detail=f"File not found: {filename}"
                )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
