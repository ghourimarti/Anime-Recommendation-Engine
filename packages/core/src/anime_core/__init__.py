"""anime_core — shared schemas, clients, and protocols.

Filled out across Steps 2 (DB + VectorIndex + embeddings), 5 (LLM client +
schemas + prompts + streaming), 7 (Cache), 8 (resilience).
"""

from anime_core.llm_client import (
    GroqClient,
    LLMClient,
    OpenAIClient,
    TieredLLMClient,
    build_default_tiered_client,
)
from anime_core.schemas import Recommendation, Recommendations

__all__ = [
    "GroqClient",
    "LLMClient",
    "OpenAIClient",
    "Recommendation",
    "Recommendations",
    "TieredLLMClient",
    "build_default_tiered_client",
]
