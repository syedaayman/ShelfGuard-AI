from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "sqlite:///shelfguard.db"
    allowed_origins: List[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]
    ngo_partners: List[str] = ["Feeding India", "Robin Hood Army", "Akshaya Patra"]
    ngo_daily_demand_threshold: int = 5  # Configurable threshold for NGO donation eligibility
    log_level: str = "INFO"
    model_path: str = "models/xgboost_pricing_model.joblib"

    # Gemini Flash Tier Config
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.6-flash"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Create a global instance
settings = Settings()
