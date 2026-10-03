"""初始化数据库：建库（如不存在）+ 建表 + 历史结构迁移（幂等）。

用法：
    APP_ENV=dev python scripts/init_db.py
    APP_ENV=prod python scripts/init_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

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

    # 3. 历史结构迁移：时间字段统一为 gmt_create / gmt_modify（幂等，保留数据）
    migrate_gmt_columns(app_engine)

    app_engine.dispose()
    print(f"[init_db] 表已创建: {', '.join(Base.metadata.tables.keys())}")
    print(f"[init_db] 环境: {settings.app_env}, 目标: {settings.db_host}:{settings.db_port}")


def migrate_gmt_columns(engine) -> None:
    """老版本表的时间列 created_at/updated_at 重命名为 gmt_create/gmt_modify（数据保留）。"""
    renames = {"articles": True, "categories": True, "tags": True, "settings": False}
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    migrated = 0
    with engine.begin() as conn:
        for table, has_create in renames.items():
            if table not in tables:
                continue
            cols = {col["name"] for col in inspector.get_columns(table)}
            clauses = []
            if has_create and "created_at" in cols and "gmt_create" not in cols:
                clauses.append("RENAME COLUMN created_at TO gmt_create")
            if "updated_at" in cols and "gmt_modify" not in cols:
                clauses.append("RENAME COLUMN updated_at TO gmt_modify")
            for clause in clauses:
                conn.execute(text(f"ALTER TABLE `{table}` {clause}"))
                migrated += 1
    if migrated:
        print(f"[init_db] 已迁移时间字段命名 -> gmt_create/gmt_modify（{migrated} 处）")


if __name__ == "__main__":
    main()
