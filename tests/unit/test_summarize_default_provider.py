from unittest.mock import patch

from media2text.core.config import SummarizeLlmConfig, SummarizeLlmProviderConfig
from media2text.core.summarize.openai_backend import resolve_llm_endpoints


@patch.dict("os.environ", {"NVIDIA_KEY": "n", "OPENAI_API_KEY": "o"}, clear=True)
def test_default_provider_model_preferred() -> None:
    cfg = SummarizeLlmConfig(
        default_provider="openai",
        default_model="gpt-4o-mini",
        providers=[
            SummarizeLlmProviderConfig(
                name="nvidia",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key_envs=["NVIDIA_KEY"],
                models=["glm"],
            ),
            SummarizeLlmProviderConfig(
                name="openai",
                base_url="https://api.openai.com/v1",
                api_key_envs=["OPENAI_API_KEY"],
                models=["gpt-4o-mini"],
            ),
        ],
    )
    eps = resolve_llm_endpoints(cfg)
    assert eps[0].provider_name == "openai"
    assert eps[0].model == "gpt-4o-mini"
