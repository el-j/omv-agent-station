FROM python:3.11-slim

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

# Install CLI coding agents (Aider, Claude Code)
RUN pip install --no-cache-dir aider-chat \
    && npm install -g @anthropic-ai/claude-code

COPY signal_bot.py .

CMD ["python", "signal_bot.py"]
