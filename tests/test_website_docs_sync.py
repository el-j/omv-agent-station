"""
Regression coverage for issue #66: website/src/pages/docs/ai-models.astro
previously claimed `gemini-3.6-flash` maps to the upstream `gemini/gemini-2.0-flash`
(it doesn't -- litellm/config.yaml maps it to `gemini/gemini-3.6-flash`) and
carried a fabricated sample router config (`deepseek-chat`, `latency-based-routing`)
that never matched the real file. These tests fail the build if the page's model
references or embedded YAML excerpts ever stop matching litellm/config.yaml again.
"""

import re
import unittest
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).parent.parent
ASTRO_PATH = ROOT_DIR / "website" / "src" / "pages" / "docs" / "ai-models.astro"
CONFIG_PATH = ROOT_DIR / "litellm" / "config.yaml"

# Single-line <code> spans on the page that are intentionally not litellm
# model_list entries (a container/service name, a file path mentioned in prose).
NON_MODEL_TOKEN_ALLOWLIST = {"litellm-proxy", "litellm/config.yaml"}


def _looks_like_model_reference(token: str) -> bool:
    """Heuristic: identifiers shaped like a litellm model_name or
    provider/model string (lowercase, hyphens/slashes/dots/colons), as opposed
    to prose, env var names (UPPERCASE), slash-commands, or bare numbers."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:-]*", token):
        return False
    if not re.search(r"[a-z]", token):
        return False
    if token[0].isupper() or token.startswith("/"):
        return False
    if "/" not in token and "-" not in token:
        return False
    if token.endswith((".yaml", ".md")):
        return False
    return True


class TestAiModelsDocSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.astro_text = ASTRO_PATH.read_text(encoding="utf-8")
        cls.config_text = CONFIG_PATH.read_text(encoding="utf-8")
        cls.config = yaml.safe_load(cls.config_text)
        cls.model_names = {d["model_name"] for d in cls.config["model_list"]}
        cls.upstream_models = {d["litellm_params"]["model"] for d in cls.config["model_list"]}
        # The docs show OpenRouter deployments in their short "provider/model:free"
        # form (without the "openrouter/" litellm prefix) for readability.
        cls.upstream_models_short = {
            m.split("openrouter/", 1)[1] if m.startswith("openrouter/") else m
            for m in cls.upstream_models
        }

    def test_embedded_yaml_excerpts_are_verbatim(self):
        """Every <pre><code> block shaped like litellm YAML must be an exact
        substring of the real config.yaml -- if config.yaml changes, this
        fails until the doc's copy-pasted excerpt is updated to match."""
        blocks = re.findall(r"<pre><code>(.*?)</code></pre>", self.astro_text, re.DOTALL)
        yaml_like_blocks = [b for b in blocks if b.lstrip().startswith(("- model_name:", "router_settings:"))]
        self.assertTrue(
            yaml_like_blocks,
            "Expected at least one litellm-config-shaped <pre><code> block in ai-models.astro",
        )
        for block in yaml_like_blocks:
            self.assertIn(
                block,
                self.config_text,
                "ai-models.astro embeds a litellm config excerpt that is no longer a "
                f"verbatim match for litellm/config.yaml:\n{block}",
            )

    def test_model_references_exist_in_config(self):
        """Every backticked model-shaped identifier on the page must resolve to
        a real model_name or upstream litellm_params.model in litellm/config.yaml."""
        # Multi-line <pre><code> blocks (the YAML excerpts, the shell command
        # examples) are covered by test_embedded_yaml_excerpts_are_verbatim or
        # aren't model references at all -- only check single-line inline spans.
        code_spans = [
            span for span in re.findall(r"<code>([^<]+)</code>", self.astro_text)
            if "\n" not in span
        ]

        checked = []
        for token in code_spans:
            if token in NON_MODEL_TOKEN_ALLOWLIST:
                continue
            if not _looks_like_model_reference(token):
                continue
            checked.append(token)
            self.assertTrue(
                token in self.model_names
                or token in self.upstream_models
                or token in self.upstream_models_short,
                f"ai-models.astro references `{token}` which is not a model_name or "
                "upstream litellm_params.model in litellm/config.yaml -- update the "
                "doc (or litellm/config.yaml if the model was renamed).",
            )

        self.assertTrue(checked, "Expected to validate at least one model identifier from ai-models.astro")
        # A couple of concrete values so a broken heuristic (e.g. one that
        # accidentally matches nothing) can't pass this test vacuously.
        self.assertIn("gemini-3.6-flash", checked)
        self.assertIn("coder-smart", checked)


if __name__ == "__main__":
    unittest.main()
