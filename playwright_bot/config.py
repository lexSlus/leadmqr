import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Settings:
    poll_interval_sec: float = float(os.getenv("TT_POLL_INTERVAL_SEC", "20"))  # как часто проверять лиды
    restart_interval_sec: int = int(os.getenv("TT_RESTART_INTERVAL_SEC", str(30)))  # полный рестарт каждые 3 часа
    proxy_url: str = os.getenv("TT_PROXY", "")
    base_url: str = os.getenv("TT_BASE", "https://www.thumbtack.com")
    leads_path: str = os.getenv("TT_LEADS_PATH", "/leads")
    email: str = os.getenv("TT_EMAIL", "wkononov@gmail.com")
    password: str = os.getenv("TT_PASSWORD", "Oleg@2025")
    storage_state: str = os.getenv("TT_STORAGE_STATE", "state.json")
    user_data_dir: str = os.getenv("TT_USER_DATA_DIR", "/app/pw_profiles/auth_setup" if os.path.exists("/app") else "./pw_profiles/auth_setup")
    headless: bool = os.getenv("TT_HEADLESS", "True")
    slow_mo: int = int(os.getenv("TT_SLOW_MO", "100"))
    message_template: str = os.getenv("TT_TEMPLATE_MESSAGE", "Hi! We can help. When is a good time to talk?")
    state_path: str = os.getenv("TT_STATE_PATH", ".taat_state.json")
    cooldown_hours: int = int(os.getenv("TT_COOLDOWN_HOURS", "0")) # if 24 that means 24 hours when you can process phone again


SETTINGS = Settings()
