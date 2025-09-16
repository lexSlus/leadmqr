import os, pathlib, re

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