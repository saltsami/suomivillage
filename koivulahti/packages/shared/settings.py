from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    env: str = "dev"
    database_url: str = "postgresql://koivulahti:koivulahti@postgres:5432/koivulahti"
    redis_url: str = "redis://redis:6379/0"
    render_queue: str = "render_jobs"
    llm_gateway_url: str = "http://llm-gateway:8081"
    sim_seed: int = 1234
    sim_tick_ms: int = 1000
    impact_threshold_feed: float = 0.6
    impact_threshold_chat: float = 0.4
    impact_threshold_news: float = 0.8
