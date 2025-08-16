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

    def phone_for_thread(self, href: str) -> Optional[str]:
        return self.data["phones_by_thread"].get(href)

    def should_skip_thread(self, href: str) -> bool:
        """
        True если тред завершён (телефон уже найден),
        либо если только что пытались (и cooldown ещё не истёк).
        """
        # 1) уже найден телефон — всегда пропускаем
        if self.phone_for_thread(href):
            return True

        # 2) телефона нет, но недавно уже пробовали
        last_ts = self.data["seen_threads"].get(href)
        if not last_ts:
            return False  # ещё не видели — пробуем

        if self.cooldown <= 0:
            # 0 => НЕ троттлим повторные попытки: пробуем каждый запуск,
            # пока не найдём телефон
            return False

        return (time.time() - last_ts) < self.cooldown