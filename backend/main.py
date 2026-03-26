#tes
import os
import json
import re
import time
import tempfile
import paramiko
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="AI DevOps Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ─────────────────────────────────────────────────────────────────────
GROQ_KEY        = os.environ.get("GROQ_KEY", "")
OPENROUTER_KEY  = os.environ.get("OPENROUTER_KEY", "")
VM_IP           = os.environ.get("VM_IP", "")
VM_USERNAME     = os.environ.get("VM_USERNAME", "")
VM_PASSWORD     = os.environ.get("VM_PASSWORD", "")
DH_USERNAME     = os.environ.get("DH_USERNAME", "")
DH_TOKEN        = os.environ.get("DH_TOKEN", "")
UI_USERNAME     = os.environ.get("UI_USERNAME", "admin")
UI_PASSWORD     = os.environ.get("UI_PASSWORD", "")

GROQ_MODEL        = "llama-3.3-70b-versatile"
OPENROUTER_MODEL  = "meta-llama/llama-3.3-70b-instruct:free"


# ── LLM caller — Groq first, OpenRouter fallback ──────────────────────────────
def call_llm(messages: list, max_tokens: int = 2048, temperature: float = 0.3) -> str:
    """Call Groq first. If it fails, fall back to OpenRouter."""

    # Try Groq
    if GROQ_KEY:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                timeout=60
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"], "groq"
        except Exception as e:
            print(f"Groq failed: {e}, trying OpenRouter...")

    # Fall back to OpenRouter
    if OPENROUTER_KEY:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/autodeploy-agent",
                    "X-Title": "AI DevOps Agent"
                },
                json={"model": OPENROUTER_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                timeout=60
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"], "openrouter"
        except Exception as e:
            raise HTTPException(500, f"Both Groq and OpenRouter failed. Last error: {e}")

    raise HTTPException(500, "No LLM configured. Set GROQ_KEY or OPENROUTER_KEY.")


# ── SSH ────────────────────────────────────────────────────────────────────────
def ssh_exec(command: str, timeout: int = 120) -> dict:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(VM_IP, username=VM_USERNAME, password=VM_PASSWORD, timeout=15)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out  = stdout.read().decode(errors='replace').strip()
        err  = stderr.read().decode(errors='replace').strip()
        code = stdout.channel.recv_exit_status()
        return {"stdout": out, "stderr": err, "exit_code": code, "success": code == 0}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "success": False}
    finally:
        client.close()


def ssh_write_file(remote_path: str, content: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(VM_IP, username=VM_USERNAME, password=VM_PASSWORD, timeout=15)
        dir_path = os.path.dirname(remote_path)
        if dir_path:
            client.exec_command(f"mkdir -p {dir_path}")
            time.sleep(0.5)
        sftp = client.open_sftp()
        with sftp.file(remote_path, 'w') as f:
            f.write(content)
        sftp.close()
    finally:
        client.close()


def find_free_port() -> int:
    r = ssh_exec("ss -tlnp | awk '{print $4}' | grep -oP ':\\K[0-9]+' | sort -n | uniq")
    used = set(int(p) for p in r["stdout"].split('\n') if p.isdigit())
    for port in range(8100, 9000):
        if port not in used:
            return port
    return 8100


# ── Models ─────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class PlanRequest(BaseModel):
    requirement: str
    history:     Optional[list] = []

class ExecuteRequest(BaseModel):
    requirement: str
    plan:        str
    history:     Optional[list] = []

class ShellRequest(BaseModel):
    command: str


# ── Auth ───────────────────────────────────────────────────────────────────────
@app.post("/auth/login")
def login(req: LoginRequest):
    if req.username == UI_USERNAME and req.password == UI_PASSWORD:
        import base64
        token = base64.b64encode(f"{req.username}:{req.password}".encode()).decode()
        return {"success": True, "token": token}
    raise HTTPException(401, "Invalid username or password")


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/")
@app.get("/health")
def health():
    groq_ok = bool(GROQ_KEY)
    or_ok   = bool(OPENROUTER_KEY)
    vm_ok   = bool(VM_IP and VM_USERNAME and VM_PASSWORD)
    return {
        "status":      "ok",
        "groq":        groq_ok,
        "openrouter":  or_ok,
        "llm_ready":   groq_ok or or_ok,
        "vm":          vm_ok,
        "docker":      bool(DH_USERNAME and DH_TOKEN),
        "active_llm":  "groq" if groq_ok else ("openrouter" if or_ok else "none"),
    }


# ── Status ─────────────────────────────────────────────────────────────────────
@app.get("/status")
def status():
    results = {}

    # Test Groq
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": GROQ_MODEL, "max_tokens": 5, "messages": [{"role": "user", "content": "ok"}]},
            timeout=10
        )
        results["groq"] = "✅ Connected" if r.status_code == 200 else f"❌ HTTP {r.status_code}"
    except Exception as e:
        results["groq"] = f"❌ {str(e)[:60]}"

    # Test OpenRouter
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": OPENROUTER_MODEL, "max_tokens": 5, "messages": [{"role": "user", "content": "ok"}]},
            timeout=10
        )
        results["openrouter"] = "✅ Connected" if r.status_code == 200 else f"❌ HTTP {r.status_code}"
    except Exception as e:
        results["openrouter"] = f"❌ {str(e)[:60]}"

    # VM SSH
    r = ssh_exec("echo ok && docker --version")
    results["vm"] = f"✅ {VM_IP}" if r["success"] else f"❌ {r['stderr'][:60]}"

    # Containers
    r2 = ssh_exec("docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'")
    results["containers"] = r2["stdout"] if r2["success"] else "Cannot list containers"

    # System
    r3 = ssh_exec("top -bn1 | grep -E 'Cpu|Mem' | head -2")
    results["system"] = r3["stdout"] if r3["success"] else ""

    all_ok = "✅" in str(results.get("vm", "")) and (
        "✅" in str(results.get("groq", "")) or "✅" in str(results.get("openrouter", ""))
    )
    results["overall"] = "✅ All systems ready" if all_ok else "⚠️ Some issues"
    return results


# ── STEP 1: Generate plan (shown to user for review) ──────────────────────────
@app.post("/plan")
def generate_plan(req: PlanRequest):
    """
    LLM generates a step-by-step plan.
    User reviews it and can approve or cancel before any execution happens.
    """
    system_prompt = f"""You are an expert AI DevOps agent. 
VM: {VM_IP} | Docker Hub: {DH_USERNAME}

A user will give you a requirement. Generate a detailed execution plan.

Format your response as:
## Plan: [title]

**What I will do:**
[clear explanation]

**Steps:**
1. [step description]
2. [step description]
...

**Expected outcome:**
[what will happen when done]

**Estimated time:** [X minutes]

Be specific about what commands will run and what files will be created.
Do NOT execute anything yet — this is just the plan for user review."""

    messages = [{"role": "system", "content": system_prompt}]
    if req.history:
        messages.extend(req.history[-6:])
    messages.append({"role": "user", "content": req.requirement})

    content, provider = call_llm(messages, max_tokens=1024, temperature=0.3)
    return {"plan": content, "provider": provider}


# ── STEP 2: Execute approved plan ─────────────────────────────────────────────
@app.post("/execute")
def execute_plan(req: ExecuteRequest):
    """
    User approved the plan. Now execute it dynamically.
    LLM generates and executes commands step by step.
    """
    system_prompt = f"""You are an expert AI DevOps agent with full control over a Linux VM.
VM IP: {VM_IP} | Docker Hub: {DH_USERNAME}

The user approved your plan. Now execute it.

To execute commands, use this exact format:
<action>
{{"tool": "shell", "command": "bash command here", "description": "what this does"}}
</action>

To write a file:
<action>
{{"tool": "write_file", "path": "/tmp/app/main.py", "content": "file content here", "description": "creating main.py"}}
</action>

To build and run a Docker image:
<action>
{{"tool": "docker_build", "path": "/tmp/app", "image_name": "myapp", "port": 8080, "description": "building and running myapp"}}
</action>

Rules:
- Execute the approved plan faithfully
- After each action result, adapt if needed
- For Python apps: write ALL files first, then build Docker image
- Always end with a clear summary of what was accomplished
- If something fails, try to fix it or explain why

Approved plan:
{req.plan}"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": f"Execute this requirement: {req.requirement}"})

    results = []
    max_iterations = 10

    for iteration in range(max_iterations):
        content, provider = call_llm(messages, max_tokens=2048, temperature=0.2)
        results.append({"type": "llm", "content": content, "provider": provider})

        actions = re.findall(r'<action>([\s\S]*?)</action>', content)
        if not actions:
            break

        exec_results = []
        for action_str in actions:
            try:
                action = json.loads(action_str.strip())
                tool   = action.get("tool", "shell")
                desc   = action.get("description", "")

                if tool == "shell":
                    cmd = action.get("command", "")
                    r   = ssh_exec(cmd)
                    exec_results.append({
                        "tool":        "shell",
                        "command":     cmd,
                        "description": desc,
                        "stdout":      r["stdout"][:3000],
                        "stderr":      r["stderr"][:500],
                        "success":     r["success"]
                    })

                elif tool == "write_file":
                    path    = action.get("path", "")
                    content_val = action.get("content", "")
                    try:
                        ssh_write_file(path, content_val)
                        exec_results.append({
                            "tool": "write_file", "path": path,
                            "description": desc, "success": True
                        })
                    except Exception as e:
                        exec_results.append({
                            "tool": "write_file", "path": path,
                            "success": False, "error": str(e)
                        })

                elif tool == "docker_build":
                    path       = action.get("path", "/tmp/app")
                    image_name = action.get("image_name", "myapp")
                    port       = action.get("port", 8080)
                    full_image = f"{DH_USERNAME}/{image_name}:latest"

                    r_build = ssh_exec(f"cd {path} && docker build -t {full_image} .", timeout=300)
                    if not r_build["success"]:
                        exec_results.append({
                            "tool": "docker_build", "success": False,
                            "error": r_build["stderr"][:500]
                        })
                        continue

                    host_port = find_free_port()
                    ssh_exec(f"docker stop {image_name} 2>/dev/null; docker rm {image_name} 2>/dev/null")
                    r_run = ssh_exec(
                        f"echo '{DH_TOKEN}' | docker login -u '{DH_USERNAME}' --password-stdin && "
                        f"docker push {full_image} && "
                        f"docker run -d --name {image_name} --restart unless-stopped "
                        f"-p {host_port}:{port} {full_image}"
                    )
                    exec_results.append({
                        "tool":      "docker_build",
                        "image":     full_image,
                        "host_port": host_port,
                        "app_url":   f"http://{VM_IP}:{host_port}",
                        "success":   r_run["success"],
                        "stdout":    r_run["stdout"][:300]
                    })

            except json.JSONDecodeError as e:
                exec_results.append({
                    "tool": "error",
                    "error": f"JSON parse error: {e}",
                    "raw": action_str[:200]
                })

        results.append({"type": "execution", "results": exec_results})
        messages.append({"role": "assistant", "content": content})
        messages.append({
            "role": "user",
            "content": f"Results:\n{json.dumps(exec_results, indent=2)}\n\nContinue or summarize if done."
        })

    return {"success": True, "iterations": iteration + 1, "results": results}


# ── Direct shell ───────────────────────────────────────────────────────────────
@app.post("/shell")
def run_shell(req: ShellRequest):
    return ssh_exec(req.command)
