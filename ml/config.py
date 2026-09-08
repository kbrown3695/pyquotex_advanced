"""Configuration stub for ML module (replaces dollar's src.config.settings)."""


class _Settings:
    """Settings configuration for ML features."""

    enable_ml_signals: bool = True
    ml_history_days: int = 30
    ml_model_dir: str = "models"


settings = _Settings()
