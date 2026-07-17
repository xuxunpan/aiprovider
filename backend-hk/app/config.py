from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 9000

    internal_secret: str = "change-me"

    openai_api_key: str = ""
    openai_base_url: str = ""
    # Responses API 的多模态对话模型（如 gpt-4.1 / gpt-4o），由其通过 image_generation 工具生图
    openai_model: str = "gpt-4.1"
    # image_generation 工具内部使用的图像模型（gpt-image-1 / gpt-image-2）
    openai_image_model: str = "gpt-image-1"
    openai_image_size: str = "1024x1024"

    storage_dir: str = "/storage"

    mock_generate: bool = False

    # Codex 会话相关
    # 模型名：留空则用 SDK 默认；常见如 gpt-5.4
    codex_model: str = ""
    codex_reasoning_effort: str = "high"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
