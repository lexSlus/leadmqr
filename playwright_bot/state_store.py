import json, os, time
from typing import Optional


class StateStore:
    def __init__(self, path: str = ".tt_state.json", cooldown_hours: int = 0):
        self.path = path
        self.cooldown = cooldown_hours * 3600  # 0 = никогда не повторять
        self.data = {
            "sent_leads": {},       # key -> timestamp
            "seen_threads": {},     # href -> timestamp
            "phones_by_thread": {}  # href -> phone
        }
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    j = json.load(f)
                    if isinstance(j, dict):
                        self.data.update(j)
            except Exception:
                pass

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---- leads ----
    def was_lead_sent(self, lead_key: str) -> bool:
        ts = self.data["sent_leads"].get(lead_key)
        if not ts:
            return False
        return (self.cooldown == 0) or (time.time() - ts < self.cooldown)

    def mark_lead_sent(self, lead_key: str):
        self.data["sent_leads"][lead_key] = time.time()
        self._save()

    # ---- threads ----
    def was_thread_seen(self, href: str) -> bool:
        ts = self.data["seen_threads"].get(href)
        if not ts:
            return False
        return (self.cooldown == 0) or (time.time() - ts < self.cooldown)

    def mark_thread_seen(self, href: str, phone: Optional[str]):
        self.data["seen_threads"][href] = time.time()
        if phone:
            self.data["phones_by_thread"][href] = phone
        self._save()