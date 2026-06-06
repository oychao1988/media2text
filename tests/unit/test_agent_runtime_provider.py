import pytest

from media2text.agent.runtime_provider import resolve_agent_provider
from media2text.core.config import AppConfig, SummarizeLlmConfig, SummarizeLlmProviderConfig

pytestmark = pytest.mark.agent


def test_resolve_agent_provider_prefers_model_owner() -> None:
    cfg = AppConfig.model_validate(
        {
            "workspace": "./data",
            "summarize": {
                "llm": {
                    "providers": [
                        {
                            "name": "nvidia",
                            "base_url": "https://integrate.api.nvidia.com/v1",
                            "models": ["deepseek-ai/deepseek-v4-pro"],
                        },
                        {
                            "name": "DeepSeek",
                            "base_url": "https://api.deepseek.com",
                            "models": ["deepseek-chat"],
                        },
                    ],
                    "default_provider": "nvidia",
                }
            },
        }
    )
    assert (
        resolve_agent_provider(
            cfg,
            model="deepseek-chat",
            provider_name="nvidia",
        )
        == "DeepSeek"
    )
