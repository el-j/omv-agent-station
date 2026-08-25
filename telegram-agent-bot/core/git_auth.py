"""
Git Authentication and Identity Provider Initializer.
Configures global git author identity and automated URL rewrites with Personal Access Tokens.
"""

import subprocess  # nosec B404
from openai import AsyncOpenAI
from .config import (
    GIT_BIN,
    GIT_AUTHOR_NAME,
    GIT_AUTHOR_EMAIL,
    GITHUB_TOKEN,
    GITLAB_TOKEN,
    BITBUCKET_USER,
    BITBUCKET_TOKEN,
    LITELLM_KEY,
    LITELLM_BASE,
    logger,
)

def init_git_credentials():
    """Configures global git identity and provider credential helpers/URL rewrites."""
    try:
        subprocess.run([GIT_BIN, "config", "--global", "user.name", GIT_AUTHOR_NAME], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "user.email", GIT_AUTHOR_EMAIL], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "init.defaultBranch", "main"], check=True)  # nosec B603,B607

        # Configure automatic token auth for GitHub
        if GITHUB_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://x-access-token:{GITHUB_TOKEN}@github.com/.insteadOf",
                "https://github.com/"
            ], check=True)
            logger.info("Configured automated git auth for GitHub.")

        # Configure automatic token auth for GitLab
        if GITLAB_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://oauth2:{GITLAB_TOKEN}@gitlab.com/.insteadOf",
                "https://gitlab.com/"
            ], check=True)
            logger.info("Configured automated git auth for GitLab.")

        # Configure automatic auth for Bitbucket
        if BITBUCKET_USER and BITBUCKET_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://{BITBUCKET_USER}:{BITBUCKET_TOKEN}@bitbucket.org/.insteadOf",
                "https://bitbucket.org/"
            ], check=True)
            logger.info("Configured automated git auth for Bitbucket.")

    except Exception as e:
        logger.warning(f"Could not configure global git credentials: {e}")

# Global async AI client pointing to local LiteLLM Proxy
ai_client = AsyncOpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1",
    timeout=120.0
)
