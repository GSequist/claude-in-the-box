# Claude-in-the-box: 
Minimal sandbox orchestration system allowing you to serve claude-code like omni-capable agents to normal users.
Claude code-like monent for normal users.

## Short tech stack: 
 - You launch Firecracker microVMs on cloud instance. 
 - Each user request creates a persistent claude agent until microVM is killed. Files and context persists between runs. 
 - Complete isolation of each microVM means claude can freely bash its way through same way claude code does in your terminal on your local machine

<sub>*The micro daemon that runs inside microVM comes from excellent e2b infrastructure repository* → https://github.com/e2b-dev/infra</sub>

## Running:

Various ways to use this:

- Simplest: your users send in task, you spin a microVM, claude works inside until done then you pull files
- Interesting: work more with the conversation -> send in previous messages from db for context and then persist what claude streams back
- More interesting: you can even use this as a teleport tool for claude -> tell him for advanced tasks he can use tool teleport, then send in context, then on tool finish, prepend claude's stream as messages to achieve continuity 

## Instructions:

<details>
<summary>0. GCP Setup (First time only) - Click to expand</summary>

Before launching any GCP instances, you need to authenticate and select your project:

0.a Authenticate with Google Cloud
```bash
# Install gcloud CLI if you don't have it
# macOS: https://cloud.google.com/sdk/docs/install

# Authenticate (opens browser for OAuth)
gcloud auth login

# Set your account
gcloud config set account your-email@example.com
```

0.b Create or Select Project
```bash
# Create new project (or use existing)
gcloud projects create sandbox-firecracker-host --name="Firecracker Sandbox"

# Set active project
gcloud config set project sandbox-firecracker-host

# Verify your config
gcloud config list
# Should show:
# [core]
# account = your-email@example.com
# project = sandbox-firecracker-host
```

0.c Enable Required APIs
```bash
# Enable Compute Engine API
gcloud services enable compute.googleapis.com

# Set default zone (optional but recommended)
gcloud config set compute/zone us-central1-a
```
</details>

<details>
<summary>1. /envd-mini instructions - Click to expand</summary>

-envd-mini contains go code to create daemon server that runs inside microVMs 
--> run GOOS=linux GOARCH=amd64 go build -o envd main.go to compile into a deamon  we will use

Verify it was built
ls -lh envd
Should show: -rwxr-xr-x ... 18M ... envd

</details>

2. /host -> host code for google cloud (allows virtualization) -> this is your firecracker host that will spin the microVMs inside

<details>
<summary>2.a and 2.b GCP Launch - Click to expand</summary>

2.a Launch GCP instance (choose spot or standard)

**Option A: Spot instance (cheaper, can be terminated by GCP)**
- Cost: ~70% cheaper than standard
- Tradeoff: GCP can terminate at any time
- Best for: Development, testing, cost-sensitive production (with auto-restart in client)

```bash
gcloud compute instances create firecracker-host \
    --zone=us-central1-a \
    --machine-type=n2-standard-4 \
    --enable-nested-virtualization \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=100GB \
    --boot-disk-type=pd-standard \
    --provisioning-model=SPOT \
    --instance-termination-action=STOP
```

**Option B: Standard instance (reliable, never terminated)**
- Cost: Regular GCP pricing (~$0.15/hr for n2-standard-4)
- Tradeoff: More expensive
- Best for: Production with guaranteed uptime

```bash
gcloud compute instances create firecracker-host \
    --zone=us-central1-a \
    --machine-type=n2-standard-4 \
    --enable-nested-virtualization \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=100GB \
    --boot-disk-type=pd-standard
    # No --provisioning-model=SPOT flag = standard instance
```

Both setups work identically. If you use spot (Option A), see the bottom of this README for client code to auto-restart terminated instances. It is easy. You can do this directly from your client, or have a separate instance orchestrating them. See below.

2.b Create firewall rule to allow port 8080

```bash
# Create firewall rule (allows HTTP traffic on port 8080)
gcloud compute firewall-rules create allow-firecracker-host \
    --allow=tcp:8080 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=firecracker-host \
    --description="Allow port 8080 for Firecracker host API"

# Add tag to your instance
gcloud compute instances add-tags firecracker-host \
    --zone=us-central1-a \
    --tags=firecracker-host
```

</details>

<details>
<summary>2.c Host dependancies - Click to expand</summary>

SSH in and install system dependencies

```bash
# SSH to the instance
gcloud compute ssh firecracker-host --zone=us-central1-a

# Update package lists
sudo apt-get update

# Install Docker, QEMU tools, and Python pip
sudo apt-get install -y docker.io jq python3-pip qemu-utils
sudo systemctl enable docker
sudo systemctl start docker

# Verify
docker --version
qemu-img --version
python3 --version
pip3 --version
```

Install Firecracker

first move to /tmp on the host
```bash
# Download Firecracker v1.9.1
wget https://github.com/firecracker-microvm/firecracker/releases/download/v1.9.1/firecracker-v1.9.1-x86_64.tgz

# Extract
tar -xzf firecracker-v1.9.1-x86_64.tgz

# Move to /usr/local/bin
sudo mv release-v1.9.1-x86_64/firecracker-v1.9.1-x86_64 /usr/local/bin/firecracker

# Make executable
sudo chmod +x /usr/local/bin/firecracker

# Verify
firecracker --version

# Clean up
rm -f firecracker-v1.9.1-x86_64.tgz
rm -rf release-v1.9.1-x86_64
```

Download Linux kernel for Firecracker

```bash
# Create kernels directory
sudo mkdir -p /opt/firecracker/kernels

# Download kernel (use Amazon's quickstart kernel)
cd /tmp
wget https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin

# Move to kernels directory
sudo mv vmlinux.bin /opt/firecracker/kernels/vmlinux
sudo chmod 644 /opt/firecracker/kernels/vmlinux

# Verify
ls -lh /opt/firecracker/kernels/vmlinux
# Should show ~13MB kernel file
```

Copy host code and install Python deps

Exit SSH (Ctrl+D), then from your local machine:

```bash
# Copy host/ directory
gcloud compute scp --recurse /[wherever this repo is]/claude_in_the_box/host/ firecracker-host:/tmp/ --zone=us-central1-a

# SSH back in
gcloud compute ssh firecracker-host --zone=us-central1-a

# Move files to /home
cd /tmp
sudo mv host/* /home/
sudo mv host/.* /home/ 2>/dev/null
sudo rm -rf host/

# Install Python dependencies (system-wide for root user)
cd /home
sudo pip3 install -r requirements.txt

# Verify structure
ls -la /home
# Should see: api_routes/, .env, app.py, auth.py, config.py, etc.
```

Setup systemd service

The systemd service ensures your FastAPI app auto-starts:

1. On spot instance restart - GCP stops/starts it, service brings it back up
2. On crash - systemd restarts it (Restart=always)
3. On manual reboot - Service starts on boot (WantedBy=multi-user.target)


From your local machine:

```bash
# Copy .service file
gcloud compute scp /path/to/claude_in_the_box/host/firecracker-host.service firecracker-host:/tmp/ --zone=us-central1-a
```

Note: the firecracker-host.service file was already copied as part of the /host dir so you can also use the one that is already there just move it to the right location (/etc/systemd/system). 


```bash
# SSH in
gcloud compute ssh firecracker-host --zone=us-central1-a

# Move service file to systemd
sudo mv /tmp/firecracker-host.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable firecracker-host.service

# Start service now
sudo systemctl start firecracker-host.service

# Check status
sudo systemctl status firecracker-host.service
```
</details>

<details>
<summary>3. Building your Claude agent image - Click to expand</summary>

You can do this either locally and then copy the finished image to Firecracker-host or copy base files and build on firecracker (copy of final image takes long because its a large file)

- in /server is claude code -> this is what will be baked into the image -> a simple FASTAPI route to get Anth. API keys from microVM (you pass them on on startup) and run claude agent in a loop -> agent uses its tools on the microVM in completely isolated safe environment, and your users can thus go crazy and give hime hard tasks -> files and context persists until microVM is killed
- add any more skills you want for claude -> i included all Anthropic excellent document skills because from normal users' perspective the work on docs is what is most impressive

3.a Build docker image that includes the daemon envd (step 1) and claude server code 

docker build -f Dockerfile-claude-fastapi -t claude-agent .

3.b convert docker image to ext4 binary that will be powering the microVMs on your firecracker-host

bash docker-img-to-ext.sh claude-agent:latest claude-agent-runtime.ext4 5120 

Note: choose the last int (5120) wisely 
1. The converter creates 5120MB ext4 empty file
2. Extracts Docker layers into it
3. Shrinks to minimum needed size
4. Expands back to 5120MB target
5. Extra space = runtime workspace for microVM
!! So if you expect Claude will need a lot of space to install additional packages into its runtime, more space.
--->larger size = more space for Claude to:
- Install packages (pip install, npm install)
- Create files in /workspace
- Download dependencies at runtime

3.c copy the final image to right location on your Firecracker-host

gcloud compute scp claude-agent-runtime.ext4 firecracker-host:/tmp/

--> move them to right loc

sudo mv /tmp/claude-agent.ext4 /opt/firecracker/images/

---> restart firecracker

sudo systemctl restart firecracker-host

</details>

<details>
<summary>4. Cron cleanup orphaned microVMs (Optional) - Click to expand</summary>

4. Cron (cleanup orphaned microVMs)

Notice `/claude_in_the_box/host/api_routes/maintenance.py` - this endpoint kills orphaned microVMs.

**Option A: Minimal setup (background task in host app.py)**

Add this to `/host/app.py`:

```python
@app.on_event("startup")
async def startup_event():
    """Start background cleanup task on app startup"""
    from api_routes.maintenance import cleanup_orphaned_resources

    async def cleanup_loop():
        while True:
            try:
                await cleanup_orphaned_resources()
            except Exception as e:
                print(f"❌ Cleanup error: {e}")
            await asyncio.sleep(60)  # Run every 60 seconds

    asyncio.create_task(cleanup_loop())
    print("✅ Started background cleanup task")
```

**Option B: More robust setup (GCP Cloud Function + Cloud Scheduler)**

Deploy the `/cron` code as a Cloud Function that periodically calls your host's `/maintenance` endpoint:

```bash
# Navigate to cron directory
cd /claude_in_the_box/cron

# Configure environment
cp .env.example .env
# Edit .env and add your HOST_API_KEY

# Edit config.py to set your domain
# INSTANCE_DOMAINS = {
#     "firecracker-host": "host.your-domain.com",
# }

# Deploy Cloud Function (Gen 2)
gcloud functions deploy cleanup-firecracker \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=lambda_handler \
  --trigger-http \
  --allow-unauthenticated \
  --set-env-vars HOST_API_KEY=your-api-key-here

# Create Cloud Scheduler job (runs every 1 minute)
gcloud scheduler jobs create http check-firecracker-cleanup \
  --location=us-central1 \
  --schedule="* * * * *" \
  --uri="https://us-central1-sandbox-firecracker-host.cloudfunctions.net/cleanup-firecracker" \
  --http-method=POST

# Verify deployment
gcloud scheduler jobs describe check-firecracker-cleanup --location=us-central1
```

The cron code checks if your host is alive first, then calls `/maintenance` to clean up zombies.

</details>

5. Running

After 3. you have active running Firecracker-host

You can play with ways to use it:

a. simplest is that you create a direct client where your users send tasks and claude works inside newly created microVM until done then you pull from it the files created (/list_workspace_files and then /download_file)

b. conversation magic -> notice that the [wherever this repo is]/claude_in_the_box/server/claude_main.py accepts "context" you can send in previous messages from your db and equally store incoming stream from claude into db to create persistence (recommended)

c. you can even use this as a teleport of sorts -> consider that in your main application claude can use this as a tool that you call teleport, you send in all recent messages for context on return you ingest new messages from claude stream to db -> this achieves a certain continuity (recommended)

d. look over the routes in [wherever this repo]/claude_in_the_box/host/api_routes/admin_routes.py -> you will see you have routes through which you can monitor and manage your Firecracker-host -> orchestration beyond the scope of this readme, but it is vry simple to use Redis and another small instance to work as your orchestrator both dividing tasks between Firecracker-hosts and keeping track which host and which microVM belongs to which user

e. ! Note: I deliberately launched a spot instance at the beginning to save you costs -> this means Google can at any time terminate the instance -> this is not a problem as you client can always directly check your instance status and then start it if needed, for example before your client sends task to claude it checks instance like:

<details>
<summary>Example - Click to expand</summary>

```
if chosen_instance.status == "TERMINATED":
    print(f"⚠️ {instance_name} is TERMINATED, starting it...")
    yield f"⚠️ Host {instance_name} is stopped, starting it...\n".encode()

    start_request = compute_v1.StartInstanceRequest(
        project="sandbox-firecracker-host",
        zone="us-central1-a",
        instance=instance_name,
    )
    operation = instances_client.start(request=start_request)

    print(f"⏳ Waiting for start operation to complete...")
    yield b"\xe2\x8f\xb3 Starting instance (this may take 30-60 seconds)...\n"

    # Poll operation completion with timeout and status updates
    operation_timeout = 120  # 2 minutes for operation
    for i in range(operation_timeout // 2):
        if operation.done():
            print(f"✅ Start operation completed")
            yield b"\xe2\x9c\x85 Start operation completed!\n"
            break
        await asyncio.sleep(2)
        if i % 10 == 0 and i > 0:
            print(f"⏳ Still waiting for start operation... ({i*2}s elapsed)")
            yield f"⏳ Still starting... ({i*2}s elapsed)\n".encode()
    else:
        print(f"⚠️ Start operation timeout, checking instance status anyway...")
        yield b"\xe2\x9a\xa0\xef\xb8\x8f Start operation timeout, checking status...\n"

    # Refresh instance status after start
    print(f"🔄 Refreshing instance status...")
    chosen_instance = instances_client.get(
        project="sandbox-firecracker-host",
        zone="us-central1-a",
        instance=instance_name,
    )
    print(f"📊 Instance status after start: {chosen_instance.status}")
```
</details>


<details>
<summary>Google instance states for ease of reference - Click to expand</summary>

**Initial States:**
- **PENDING**: Flex-start VMs enter this state while Compute Engine attempts to acquire resources within
the specified wait time.
- **PROVISIONING**: "Compute Engine allocates resources for the instance" after creation, restart, or
resume.

**Active States:**
- **STAGING**: "Compute Engine is preparing the instance for first boot" but it isn't running yet.
- **RUNNING**: The instance is booting or operational, allowing stop, suspend, or delete operations.

**Shutdown States:**
- **PENDING_STOP**: "The instance is gracefully shutting down" when graceful shutdown is enabled.
- **STOPPING**: "The instance is shutting down its guest OS" during normal stops or deletions.
- **TERMINATED**: "Compute Engine has completed the stop operation" with resources remaining attached.

**Maintenance State:**
- **REPAIRING**: "Compute Engine is repairing the instance" due to internal errors or host
unavailability.

**Suspension States:**
- **SUSPENDING**: Suspend operation initiated by the user.
- **SUSPENDED**: Suspend operation completed; instance can remain suspended up to 60 days before
automatic termination

</details>

<details>
<summary>6. (Optional) Domain + SSL - Click to expand</summary>

6. (Optional) Domain + SSL

For production, put your firecracker-host behind a domain with SSL.

**6.a Get static IP**
```bash
# Reserve static IP
gcloud compute addresses create firecracker-host-ip --region=us-central1

# Get the IP (save this)
gcloud compute addresses describe firecracker-host-ip --region=us-central1 --format="get(address)"

# Attach to instance
gcloud compute instances delete-access-config firecracker-host --zone=us-central1-a --access-config-name="external-nat"
gcloud compute instances add-access-config firecracker-host --zone=us-central1-a --access-config-name="external-nat" \
    --address=$(gcloud compute addresses describe firecracker-host-ip --region=us-central1 --format="get(address)")
```

**6.b Domain + DNS**

1. Buy domain (Namecheap, Cloudflare, etc.)
2. Add DNS A record: `host.yourdomain.com` → your static IP
3. Wait 5-10 min for DNS propagation

**6.c SSL with certbot**

SSH into firecracker-host:
```bash
gcloud compute ssh firecracker-host --zone=us-central1-a

# Install
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --standalone -d host.yourdomain.com --agree-tos -m your@email.com

# Edit nginx to add IP whitelist (recommended)
sudo nano /etc/nginx/sites-available/default

# Add before server block:
#   geo $allowed_ip {
#       default 0;
#       YOUR.IP.here.for.testing 1;
#   }
#
# Add inside server block:
#   if ($allowed_ip = 0) { return 403; }
#
# Add location block:
#   location / {
#       proxy_pass http://127.0.0.1:8080;
#       proxy_set_header Host $host;
#   }

# Reload
sudo nginx -t && sudo systemctl reload nginx
```

Certbot auto-renews. Done.

</details>

## Testing

<details>
<summary>Click to expand: Complete curl testing commands</summary>

```bash
# Set API_KEY to terminal
API_KEY="X"

# Host endpoint (include http:// and port :8080)
SANDBOX="http://YOUR_GCP_IP:8080"

ANTHROPIC_API_KEY=""
```

## 1. Create MicroVM

### Claude Agent Runtime (with API key)
```bash
curl -X POST "$SANDBOX/create_microvm" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\"user_id\": \"test-claude-1\", \"runtime\": \"claude-agent\", \"env_vars\": {\"ANTHROPIC_API_KEY\": \"$ANTHROPIC_API_KEY\"}}"
```

**Expected Response:**
```json
{"status": "created", "vm_ip": "10.0.1.100", "pid": 1234}
```

**Timing:**
- Python/Node/Bash: ~3-5 seconds
- Claude: ~5-8 seconds (larger image)

---

## 2. Task Execution

### Simple Task
```bash
curl -N --max-time 300 -X POST "$SANDBOX/claude_in_the_box" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"user_id": "test-claude-1", "task": "Create a Python script that prints hello world", "files": {}}'
```

### Task with Files
```bash
curl -N --max-time 300 -X POST "$SANDBOX/claude_in_the_box" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"user_id": "test-claude-1", "task": "Run the hello.py script", "files": {"hello.py": "print(\"Hello World\")"}}'
```

the hello.py must be in the cd where you are running the cmd from

**Note:** The `-N` flag disables buffering to see streaming output in real-time, and `--max-time 300` sets a 5-minute timeout.

**Expected Response:**
Streaming JSON events:
```json
{"type": "text", "content": "I'll help you..."}
{"type": "tool_use", "content": {...}}
{"type": "completion", "content": "Done!"}
```

---

## 4. List files created inside the microVM

```bash
curl -X GET "$SANDBOX/list_workspace_files?user_id=test-claude-1" \
  -H "X-API-Key: $API_KEY" \
```

---

## 5. Download file


```bash
curl -X GET "$SANDBOX/download_file?user_id=test-claude-1&filename=hello.py" \
  -H "X-API-Key: $API_KEY"
  -o hello.py
```

the -o flag saves it to cd wherever u run the cmd from!

---

## 6. List running processes

```bash
curl -X GET "$SANDBOX/list_processes?user_id=test-claude-1" \
  -H "X-API-Key: $API_KEY"
```

---

## Admin Get Status

```bash
curl -X GET "$SANDBOX/status" \
  -H "X-API-Key: $API_KEY"
```

---

## Admin Kill MicroVM

```bash
curl -X POST "$SANDBOX/kill_microvm" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id": "test-claude-1"}'
```

---

## Admin Health Check

```bash
curl -X GET "$SANDBOX/health"
```

---

</details>