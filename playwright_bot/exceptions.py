"""
Исключения для Browser Service API и LeadRunner.
"""


class BrokerError(Exception):
    """Базовый класс для ошибок Browser Service API"""
    pass


class AccountLockedError(BrokerError):
    """Аккаунт заблокирован другим воркером (423)"""
    pass


class NoBrowsersAvailableError(BrokerError):
    """Нет доступных браузеров в пуле (503)"""
    pass

