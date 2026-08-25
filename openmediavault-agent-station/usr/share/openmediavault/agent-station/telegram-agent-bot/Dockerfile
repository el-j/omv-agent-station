FROM python:3.11-slim

# Install system utilities, git, tmux, curl, nodejs for coding tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    tmux \
    curl \
    ca-certificates \
    build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install CLI coding agents (Aider, Claude Code, etc.)
RUN pip install --no-cache-dir aider-chat \
    && npm install -g @anthropic-ai/claude-code

COPY bot.py .

CMD ["python", "bot.py"]
