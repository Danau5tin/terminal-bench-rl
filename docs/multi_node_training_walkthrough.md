# Multi-Node Training Setup for bare metal GPU clusters

## Prerequisites
- Multiple nodes with SSH access
- Root access on all nodes
- Internal network connectivity between nodes

## Setup Steps

### 1. Initial Setup (All Nodes)
```bash
# Install Docker
echo "Updating package index..."
sudo apt-get update -y

# Install prerequisites
echo "Installing prerequisites..."
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
echo "Adding Docker GPG key..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo "Setting up Docker repository..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
echo "Installing Docker Engine..."
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add current user to docker group
echo "Adding $USER to docker group..."
sudo usermod -aG docker $USER

# This configuration creates much smaller subnets (size /24),
# which dramatically increases the number of available networks from ~31 to over 500.
# This prevents the 'all predefined address pools have been fully subnetted' error.
echo "Configuring Docker daemon for a high number of networks..."
sudo mkdir -p /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
  "default-address-pools": [
    {"base": "172.17.0.0/16", "size": 24},
    {"base": "192.168.0.0/16", "size": 24}
  ],
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10
}
EOF

echo "Restarting and enabling Docker service to apply new configuration..."
sudo systemctl restart docker
sudo systemctl enable docker

echo ""
echo "Docker installation and configuration complete!"
echo "IMPORTANT: Please log out and back in for the group changes to take effect."
```

### 2. Setup Shared Storage (NFS)

**On Head Node (Node 1):**
```bash
# Setup NFS server
sudo apt-get update && sudo apt-get install -y nfs-kernel-server
sudo mkdir -p /mnt/shared
sudo chown $USER:$USER /mnt/shared
echo "/mnt/shared *(rw,sync,no_subtree_check,no_root_squash)" | sudo tee -a /etc/exports
sudo systemctl restart nfs-kernel-server

hostname -I | awk '{print $1}'  # Note this IP for next step
```

**On All Worker Nodes:**
```bash
# Mount shared storage (replace <HEAD_INTERNAL_IP> with actual IP)
sudo apt-get update && sudo apt-get install -y nfs-common
sudo mkdir -p /mnt/shared
sudo mount <HEAD_INTERNAL_IP>:/mnt/shared /mnt/shared

# Make permanent
echo "<HEAD_INTERNAL_IP>:/mnt/shared /mnt/shared nfs defaults 0 0" | sudo tee -a /etc/fstab

# Verify
df -h | grep shared
```

### 3. Clone Repository and Setup Local Environment on each node

**On Head Node Only:**
```bash
# Clone into shared storage
cd /mnt/shared
git clone --recurse-submodules https://github.com/Danau5tin/terminal_bench_rl.git
cd ~
```

**On All Nodes (including head):**
```bash
# Install uv first
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Set venv to be created in home directory (not shared)
export UV_PROJECT_ENVIRONMENT=$HOME/terminal_bench_venv

# Work from shared code, but venv will be local
cd /mnt/shared/terminal_bench_training
uv venv  # Creates venv at $HOME/terminal_bench_venv
git submodule update --init --recursive
uv sync
uv pip install torch
uv pip install --no-build-isolation flash-attn
cd external/rllm
uv pip install -e ./verl[vllm,gpu]
uv pip install -e .
cd ../..
uv pip install "vllm==0.9.1"

source $HOME/terminal_bench_venv/bin/activate
```

### 4. Set File Descriptor Limits (ALL Nodes)

```bash
# Set for current session
ulimit -n 65536

# Set permanent limits
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "root soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "root hard nofile 65536" | sudo tee -a /etc/security/limits.conf

# Set system-wide limits for services (including Ray)
sudo mkdir -p /etc/systemd/system.conf.d/
echo "[Manager]
DefaultLimitNOFILE=65536" | sudo tee /etc/systemd/system.conf.d/limits.conf

# Reload systemd
sudo systemctl daemon-reload

# Log out and back in for limits to take effect
echo "exit and return for limits to take effect"

# After logging back in, verify:
ulimit -n  # Should show 65536
```

### 5. Configure Network Environment

**Find Network Interface (on all nodes):**
```bash
# Get your network interface name
ip route | grep default
# Example output: default via 10.15.22.38 dev enp27s0f0np0 proto static
# So interface is: enp27s0f0np0
```

**Set Environment Variables (on all nodes):**
```bash
# IMPORTANT: Replace with the node's actual interface from above!
# **Each node may have a different interface name**
export GLOO_SOCKET_IFNAME=<YOUR_INTERFACE>  # e.g., enp157s0f0np0 or enp27s0f0np0
export NCCL_SOCKET_IFNAME=<YOUR_INTERFACE>
export MASTER_ADDR=<HEAD_INTERNAL_IP>
export MASTER_PORT=29500

# Additional Gloo settings
export TP_SOCKET_IFNAME=<YOUR_INTERFACE>
export GLOO_SKIP_DEVICE_INTERFACES=lo
export GLOO_USE_IPV4=1
export GLOO_TIMEOUT_MS=60000

# NCCL settings for Ethernet (no InfiniBand)
export NCCL_IB_DISABLE=1
export NCCL_P2P_DISABLE=1
export NCCL_TREE_THRESHOLD=0
export NCCL_NET_GDR_LEVEL=0
export NCCL_CROSS_NIC=1
export NCCL_SHM_DISABLE=1
export NCCL_TIMEOUT_MS=1800000
export NCCL_ASYNC_ERROR_HANDLING=0

# Debugging (optional)
export TORCH_DISTRIBUTED_DEBUG=DETAIL
export NCCL_DEBUG=INFO
```

**On worker nodes:**
This is done automatically on the head node within the launch script
```bash
export TOKENIZERS_PARALLELISM=true
export NCCL_DEBUG=WARN
export PYTHONPATH="$(pwd):$(pwd)/external/rllm"

export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:False"

export VLLM_ATTENTION_BACKEND=FLASH_ATTN
export VLLM_USE_V1=1 
export VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
export VLLM_ENGINE_ITERATION_TIMEOUT_S=100000000000
```

### 7. Check Firewall Rules
```bash
# Check if iptables is blocking
sudo iptables -L -n | grep -E "DROP|REJECT"

# If you see DROP rules, add exception for internal subnet
sudo iptables -I FORWARD -s 10.15.22.0/24 -d 10.15.22.0/24 -j ACCEPT
sudo iptables -I FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT
```

### 8. Start Ray with Environment

**On Head Node:**
```bash
# Start Ray with all environment variables set
ray start --head --port=6379 --dashboard-host=0.0.0.0
```

**On Worker Nodes:**
```bash
# Start Ray with environment
ray start --address='<HEAD_INTERNAL_IP>:6379'
```

**Verify cluster:**
```bash
ray status  # Should show all nodes with GPUs
```

### 9. Verify Package Versions Match

**On all nodes:**
```bash
cd /mnt/shared/terminal_bench_training
source $HOME/terminal_bench_venv/bin/activate

# Check versions - MUST match across all nodes!
uv pip list | grep -E "transformers|vllm|torch"

# If versions don't match, synchronize them:
# Example: uv pip install "transformers==4.51.3"
# Sometimes this happens after running script for the first time, presumably as frameworks alter required versions at runtime
```

### 10. Prepare dataset
```bash
mkdir tasks/
# Create an example task, this is required for the script to run successfully because tb's first start up requires user interaction
tb tasks create example_task_001 \
  --name "Dan Austin" \
  --email "dan@aituning.ai" \
  --category "general" \
  --difficulty "easy" \
  --instruction "Write a Python function that calculates the factorial of a number" \
  --tag "python" \
  --tag "algorithms" \
  --no-interactive

  # Answer n to first question, then y to second, and then task will create
```

# Convert tasks
```bash
# Remove example task just created
rm -rf tasks/
mkdir tasks/

# Convert the dataset to tasks
python dataset/convert_dataset_to_tasks.py --workers 40
# Often fails a few datapoints (~5) first time as `tb` gets going, so run again. 
# Safe to do so as only failed tasks will be created. Already created tasks will be skipped.
python dataset/convert_dataset_to_tasks.py --workers 40

mkdir -p data/terminal_bench
python dataset/tasks_to_parquet_converter.py
```

### 11. Launch Training

**On Head Node:**
```bash
# Set training environment variables
export WANDB_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export HF_TOKEN="your-token"
export HF_USERNAME="your-username"
export LLM_JUDGE_NAME="anthropic/claude-sonnet-4-20250514"

# Launch training
python scripts/launch_training.py prod_32b_2x8_h100  # For 2 nodes
# or
python scripts/launch_training.py prod_32b_4x8_h100  # For 4 nodes
```

## Common Issues and Solutions

### 1. "Too many open files" error
- Solution: `ulimit -n 65536` before running

### 2. "Gloo connectFullMesh failed" error
- Solution: Set GLOO_SOCKET_IFNAME to correct interface (not eth0!)
- Must restart Ray after setting environment variables
- Interface names can be different on each node (e.g., enp157s0f0np0 vs enp27s0f0np0)

### 3. "aimv2 is already used by a Transformers config" error
- Solution: Ensure all nodes have same transformers version
- Downgrade if needed: `uv pip install "transformers==4.51.3"`

### 4. NCCL network errors
- Solution: Use the NCCL environment variables for Ethernet (not InfiniBand)
- Disable P2P and shared memory for cross-node communication

### 5. Ray tasks not scheduling
- Solution: Ensure Ray is started AFTER setting all environment variables
- Check `ray status` shows all nodes and GPUs

## Accessing Ray Dashboard

The Ray dashboard runs on the private network and needs SSH port forwarding to access from your local machine.

**Setup SSH Port Forwarding:**
```bash
# Replace with your actual SSH key path and head node's public IP
ssh -i ~/.ssh/id_ed25519_hyperbolic -L 8265:<HEAD_INTERNAL_IP>:8265 ubuntu@<HEAD_PUBLIC_IP>

# Example:
ssh -i ~/.ssh/id_ed25519_hyperbolic -L 8265:10.15.22.33:8265 ubuntu@147.185.41.21
```

**Access Dashboard:**
Once the SSH tunnel is established, open your browser and go to:
```
http://localhost:8265
```

## Optional

### nvtop - Interactive GPU Process Viewer
`nvtop` provides a nice interactive interface showing GPU utilization, memory usage, temperature, and running processes in real-time (similar to htop but for GPUs).

```bash
sudo apt install nvtop
```

## tmux - keep things in the bg
```bash
cd ~/terminal-bench-rl

# Install tmux
sudo apt-get update && sudo apt-get install -y tmux
```