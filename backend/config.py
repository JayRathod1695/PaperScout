from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str
    supabase_jwt_secret: str

    # AI Model
    ai_model_api_key: str
    nvidia_api_key: str = ""
    base_url: str = ""

    # OpenAlex
    openalex_api_key: str = ""

    # Brevo
    brevo_api_key: str
    brevo_sender_email: str = "jay.rathod1695@gmail.com"
    brevo_sender_name: str = "PaperScout"

    # App config
    frontend_url: str = "http://localhost:3000"
    environment: str = "development"
    max_text_length: int = 100_000
    max_related_papers: int = 8
    ai_call_delay_seconds: float = 4.5

    class Config:
        env_file = ".env"

settings = Settings()
