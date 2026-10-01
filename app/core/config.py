"""应用配置：通过 APP_ENV 区分 dev / prod，加载对应的 .env.{env} 文件。

优先级：真实环境变量 > .env.{APP_ENV} 文件 > 代码默认值。
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ENV = os.getenv("APP_ENV", "dev").strip().lower() or "dev"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=f".env.{APP_ENV}",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = APP_ENV
    app_name: str = "blog"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # ---- 数据库 ----
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = "root"
    db_name: str = "blog"
    db_echo: bool = False

    # ---- 语雀导入 ----
    # 「导入语雀文章」抓取公开文档的基址（一般不用改）
    yuque_import_base: str = "https://www.yuque.com"

    # ---- 管理端 ----
    admin_username: str = "admin"
    admin_password: str = "admin123"
    jwt_secret: str = "change-me-in-prod-please-use-a-long-random-secret"
    jwt_expire_minutes: int = 60 * 24

    # ---- 站点 ----
    site_title: str = "My Blog"
    site_description: str = ""
    cors_origins: str = "*"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def database_url_no_db(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
