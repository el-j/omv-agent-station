FROM tsl0922/ttyd:latest AS ttyd-src

FROM node:22-bookworm-slim

# Copy pre-compiled ttyd binary
COPY --from=ttyd-src /usr/bin/ttyd /usr/bin/ttyd

# Install system utilities, python, git, tmux, gh (GitHub CLI)
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
    gh \
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
