from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    backend: str
    endpoint: str
    model: str
    service_url: str = ""
    service_token: str = ""

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            Path(os.getenv("MATRIX_DATA_DIR") or ROOT / "data").expanduser(),
            os.getenv("MATRIX_BACKEND", "jev"),
            os.getenv("MATRIX_API_ENDPOINT", ""),
            os.getenv("MATRIX_API_MODEL", ""),
            os.getenv("MATRIX_JEVDB_SERVICE_URL", ""),
            os.getenv("MATRIX_JEVDB_SERVICE_TOKEN", ""),
        )

    @property
    def credential_available(self):
        return bool(os.getenv("JEV_API_KEY" if self.backend == "jev" else "OPENAI_API_KEY"))
