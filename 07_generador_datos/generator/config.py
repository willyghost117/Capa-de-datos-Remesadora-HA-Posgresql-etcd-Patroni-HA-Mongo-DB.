from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GeneratorConfig:
    raw: dict[str, Any]
    base_dir: Path

    @property
    def postgres_dsn(self) -> str:
        pg = self.raw["postgres"]
        password = os.getenv(pg.get("password_env", "GLOBALREMIT_PG_PASSWORD"), "")
        parts = [
            f"host={pg['host']}",
            f"port={pg['port']}",
            f"dbname={pg['database']}",
            f"user={pg['user']}",
        ]
        if password:
            parts.append(f"password={password}")
        return " ".join(parts)

    @property
    def mongo_uri(self) -> str:
        return self.raw["mongodb"]["uri"]

    @property
    def mongo_database(self) -> str:
        return self.raw["mongodb"]["database"]

    @property
    def mongo_enabled(self) -> bool:
        return bool(self.raw["mongodb"].get("enabled", True))

    @property
    def output_dir(self) -> Path:
        return (self.base_dir / self.raw["output"]["directory"]).resolve()

    @property
    def report_path(self) -> Path:
        return (self.base_dir / self.raw["output"]["report_path"]).resolve()

    @property
    def cleanup_generated_data(self) -> bool:
        return bool(self.raw.get("cleanup_generated_data", True))


def load_config(path: str | Path) -> GeneratorConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return GeneratorConfig(raw=raw, base_dir=config_path.parent)
