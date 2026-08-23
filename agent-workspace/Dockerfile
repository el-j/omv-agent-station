FROM node:22-bookworm-slim

# Install system utilities, python, git, github CLI, tmux, ttyd
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    tmux \
    curl \
    wget \
    jq \
    ripgrep \
    openssh-client \
    ca-certificates \
    procps \
    ttyd \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y github-cli \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Create workspace and obsidian directories
RUN mkdir -p /workspace /obsidian /home/agent/.claude /home/agent/.ssh \
    && useradd -u 1000 -U -d /home/agent -s /bin/bash agent 2>/dev/null || true \
    && chown -R 1000:1000 /workspace /obsidian /home/agent

USER agent
WORKDIR /workspace

ENV HOME=/home/agent
ENV PATH=/usr/local/bin:/usr/bin:/bin:/home/agent/.local/bin

EXPOSE 7681

CMD ["ttyd", "-p", "7681", "-W", "tmux", "new-session", "-A", "-s", "agent-main", "-c", "/workspace", "bash"]
