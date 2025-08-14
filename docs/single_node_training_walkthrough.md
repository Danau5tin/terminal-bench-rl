# Single-Node Training Setup for VM GPU instance

## Prerequisites
- SSH access to node

## Setup Steps

### 1. Install docker
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

### 2. Clone and setup repo
```bash
git clone --recurse-submodules https://github.com/Danau5tin/terminal-bench-rl.git
cd terminal-bench-rl

curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

uv venv
git submodule update --init --recursive
uv sync
uv pip install torch
uv pip install --no-build-isolation flash-attn
cd external/rllm
uv pip install -e ./verl[vllm,gpu]
uv pip install -e .
cd ../..
# Required after v0.10.0 was released
uv pip install "vllm==0.9.1"

source .venv/bin/activate

export WANDB_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export HF_TOKEN="your-token"
export HF_USERNAME="your-username"
export LLM_JUDGE_NAME="anthropic/claude-sonnet-4-20250514"
```

### 3. Prepare dataset
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

### 4. Convert tasks
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

### 5. Launch training
```bash
python training_scripts/launch_training.py test_8b_2_gpus  # Run `python scripts/launch_training.py list` for all configs
```


## Optional

### nvtop - Interactive GPU Process Viewer
`nvtop` provides a nice interactive interface showing GPU utilization, memory usage, temperature, and running processes in real-time (similar to htop but for GPUs).

```bash
sudo apt install nvtop
```

## tmux - keep things in the bg
```bash
cd ~/terminal_bench_training

# Install tmux
sudo apt-get update && sudo apt-get install -y tmux
```
