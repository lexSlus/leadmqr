import os, pathlib, re
from typing import Optional, Dict
import time
from datetime import datetime, timezone
import redis


def unique_user_data_dir(role: str) -> str:
    """
    role: 'producer' | 'worker' — для читаемости.
    Возвращает уникальный user_data_dir для текущего процесса (HOSTNAME+PID),
    создаёт папку и чистит возможные лок-файлы Chromium.
    """
    base = os.getenv("TT_USER_DATA_DIR", "/app/pw_profiles").rstrip("/")
    hostname = os.getenv("HOSTNAME", "host")
    pid = os.getpid()
    wname = os.getenv("CELERY_WORKER_NAME", "")
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", wname) if wname else "proc"
    path = f"{base}/{role}-{hostname}-{pid}-{safe}"
    p = pathlib.Path(path)
    p.mkdir(parents=True, exist_ok=True)
    for f in p.glob("Singleton*"):
        try:
            f.unlink()
        except Exception:
            pass
    return path



class FlowTimer:
    """
    Сквозная телеметрия этапов по lead_key.

    Пример стадий:
      detect → enqueued → task_start → phone_found → ai_enqueued → call_started
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "flow",
        ttl_seconds: int = 2 * 24 * 3600,  # 2 дня
        decode_responses: bool = True,
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://leadmqr_redis:6379/0")
        self.r = redis.Redis.from_url(self.redis_url, decode_responses=decode_responses)
        self.prefix = key_prefix.rstrip(":")
        self.ttl = ttl_seconds

    def _key(self, lead_key: str) -> str:
        return f"{self.prefix}:{lead_key}"

    def mark(self, lead_key: str, stage: str) -> None:
        """
        Поставить отметку для стадии.
        Пишем и читаемое wall-время (ISO UTC), и монотонное время (ns) для точных дельт.
        """
        now_wall = datetime.now(timezone.utc).isoformat()
        now_mono = time.monotonic_ns()
        self.r.hset(
            self._key(lead_key),
            mapping={f"{stage}:wall": now_wall, f"{stage}:mono": now_mono},
        )
        self.r.expire(self._key(lead_key), self.ttl)

    def durations(self, lead_key: str) -> Dict[str, Optional[float]]:
        """
        Вернуть словарь с дельтами по основным этапам (в секундах).
        """
        h = self.r.hgetall(self._key(lead_key))

        def m(st: str) -> Optional[int]:
            v = h.get(f"{st}:mono")
            return int(v) if v is not None else None

        def diff(a: str, b: str) -> Optional[float]:
            A, B = m(a), m(b)
            return round((B - A) / 1e9, 3) if A is not None and B is not None else None

        return {
            "total_s": diff("detect", "call_started"),
            "detect_to_enqueued_s": diff("detect", "enqueued"),
            "enqueued_to_task_start_s": diff("enqueued", "task_start"),
            "task_start_to_phone_found_s": diff("task_start", "phone_found"),
            "phone_found_to_ai_enqueued_s": diff("phone_found", "ai_enqueued"),
            "ai_enqueued_to_call_started_s": diff("ai_enqueued", "call_started"),
        }

    def snapshot(self, lead_key: str) -> Dict[str, str]:
        """
        Сырые значения (все поля hash) — удобно для дебага.
        """
        return self.r.hgetall(self._key(lead_key))

    def clear(self, lead_key: str) -> None:
        """Удалить все отметки по лиду (напр., перед повторным тестом)."""
        self.r.delete(self._key(lead_key))