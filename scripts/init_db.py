"""初始化数据库：建库（如不存在）+ 建表。

用法：
    APP_ENV=dev python scripts/init_db.py
    APP_ENV=prod python scripts/init_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db import models  # noqa: F401,E402  确保模型注册
from app.db.base import Base  # noqa: E402


def main() -> None:
    settings = get_settings()

    # 1. 建库
    server_engine = create_engine(settings.database_url_no_db, pool_pre_ping=True)
    with server_engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
        conn.commit()
    server_engine.dispose()
    print(f"[init_db] 数据库已就绪: {settings.db_name}")

    # 2. 建表
    app_engine = create_engine(settings.database_url, pool_pre_ping=True)
    Base.metadata.create_all(app_engine)
    app_engine.dispose()
    print(f"[init_db] 表已创建: {', '.join(Base.metadata.tables.keys())}")
    print(f"[init_db] 环境: {settings.app_env}, 目标: {settings.db_host}:{settings.db_port}")


if __name__ == "__main__":
    main()
