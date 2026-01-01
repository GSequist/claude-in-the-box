from connectrpc.method import MethodInfo, IdempotencyLevel
import process_pb2
from typing import Dict
from pydantic import BaseModel


class CreateMicroVMRequest(BaseModel):
    user_id: str
    runtime: str = "python"
    env_vars: Dict[str, str] = {}


class TaskRequest(BaseModel):
    user_id: str
    task: str
    context: list[dict] = []
    files: Dict[str, str] = {}


class KillMicroVMRequest(BaseModel):
    user_id: str


# In-memory tracking of microVMs:
# {user_id: {
#     "process": subprocess.Popen,
#     "ip": "10.0.1.100",
#     "running_process_pid": None,  # REPL kernel PID
#     "background_process_pid": None  # Background server PID (only one allowed)
# }}

microvms: Dict[str, dict] = {}

# Configuration
FIRECRACKER_BIN = "/usr/local/bin/firecracker"
KERNEL_PATH = "/opt/firecracker/kernels/vmlinux"
WORK_DIR = "/opt/firecracker/vms"

# Runtime image mappings ->
ROOTFS_IMAGES = {
    "claude-agent": "/opt/firecracker/images/claude-agent-runtime.ext4",
}

# IP allocation (simple counter for now)
next_ip = 100  # Will assign 10.0.1.100, 10.0.1.101, etc.

# Define RPC methods once (reused across all calls)
START_METHOD = MethodInfo(
    name="Start",
    service_name="process.Process",
    input=process_pb2.StartRequest,
    output=process_pb2.StartResponse,
    idempotency_level=IdempotencyLevel.NO_SIDE_EFFECTS,
)
