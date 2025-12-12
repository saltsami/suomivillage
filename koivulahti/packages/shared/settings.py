from pydantic import BaseSettings


class Settings(BaseSettings):
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

    class Config:
        env_prefix = ""
