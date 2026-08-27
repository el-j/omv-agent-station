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

# Create workspace and obsidian directories using existing node user (UID 1000)
RUN mkdir -p /workspace /obsidian /home/node/.claude /home/node/.ssh \
    && chown -R node:node /workspace /obsidian /home/node

USER node
WORKDIR /workspace

ENV HOME=/home/node
ENV PATH=/usr/local/bin:/usr/bin:/bin:/home/node/.local/bin

EXPOSE 7681

CMD ["ttyd", "-p", "7681", "-W", "tmux", "new-session", "-A", "-s", "agent-main", "-c", "/workspace", "bash"]
