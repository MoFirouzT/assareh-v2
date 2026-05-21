from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASSAREH_", env_file=".env")

    # Paths
    data_dir: Path = Path("data")
    raw_subdir: str = "raw"
    interim_subdir: str = "interim"
    external_subdir: str = "external"

    # Data
    symbol: str = "BTCUSDT"
    intervals: list[str] = ["1m", "15m", "1h", "4h"]

    # Experiment tracking
    mlflow_tracking_uri: str = "file:./mlruns"

    # Misc
    random_seed: int = 42
    log_level: str = "INFO"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / self.raw_subdir

    @property
    def interim_dir(self) -> Path:
        return self.data_dir / self.interim_subdir

    @property
    def external_dir(self) -> Path:
        return self.data_dir / self.external_subdir
