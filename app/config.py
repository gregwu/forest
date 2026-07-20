from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_db: str = "forest"
    mongo_user: str | None = None
    mongo_password: str | None = None

    secret_key: str = "dev-secret-change-me"
    pages_dir: str = "./pages"
    session_cookie: str = "forest_session"
    base_path: str = ""

    @property
    def mongo_url(self) -> str:
        if self.mongo_user and self.mongo_password:
            return f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}"
        return f"mongodb://{self.mongo_host}:{self.mongo_port}"


settings = Settings()
