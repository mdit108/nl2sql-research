"""Prompt construction. The template is a versioned file under prompts/; code only fills slots."""

import hashlib
from dataclasses import dataclass
from functools import lru_cache

from app.config import PROJECT_ROOT

PROMPTS_DIR = PROJECT_ROOT / "prompts"
DEFAULT_PROMPT = "generation/v1"


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    text: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:12]

    def render(self, question: str, context: str) -> str:
        # Blank-line padding around context keeps E0 (no context) and E1+ equally formatted.
        block = f"\n{context}\n" if context else ""
        return self.text.replace("{context}", block).replace("{question}", question.strip())


@lru_cache
def load_prompt(version: str = DEFAULT_PROMPT) -> PromptTemplate:
    return PromptTemplate(version=version, text=(PROMPTS_DIR / f"{version}.md").read_text())
