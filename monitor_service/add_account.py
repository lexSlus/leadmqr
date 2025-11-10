#!/usr/bin/env python3
"""
Скрипт для добавления аккаунта в базу данных.
"""
import asyncio
import sys
import os
import logging

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(__file__))

from monitor_service.database.database import AsyncSessionLocal, init_db
from monitor_service.database.crud import accounts
from monitor_service.database.schemas import AccountCreate

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def add_account(email: str, password: str, account_id: str = None, enabled: bool = True, auto_update_password: bool = False):
    """
    Добавляет аккаунт в базу данных.
    
    Args:
        email: Email аккаунта
        password: Пароль аккаунта
        account_id: ID аккаунта (если не указан, используется часть email)
        enabled: Активен ли аккаунт (по умолчанию True)
        auto_update_password: Автоматически обновить пароль если аккаунт существует (без подтверждения)
    """
    if not account_id:
        # Генерируем account_id из email (часть до @)
        account_id = email.split("@")[0]
    
    logger.info("=" * 60)
    logger.info("ДОБАВЛЕНИЕ АККАУНТА В БД")
    logger.info("=" * 60)
    logger.info(f"Account ID: {account_id}")
    logger.info(f"Email: {email}")
    logger.info(f"Enabled: {enabled}")
    logger.info("")
    
    try:
        # Инициализируем БД
        await init_db()
        
        # Создаем сессию БД
        async with AsyncSessionLocal() as db:
            # Проверяем, существует ли аккаунт с таким email
            existing = await accounts.get_account_by_email(db, email)
            if existing:
                logger.warning(f"⚠️  Аккаунт с email {email} уже существует!")
                logger.info(f"   Account ID: {existing.account_id}")
                logger.info(f"   Enabled: {existing.enabled}")
                
                # Спрашиваем, обновить ли пароль (если не указан флаг auto_update_password)
                if auto_update_password:
                    response = 'y'
                else:
                    response = input("\nОбновить пароль? (y/n): ").strip().lower()
                
                if response == 'y':
                    # Обновляем пароль
                    from monitor_service.database.schemas import Account
                    from monitor_service.database.crud.accounts import update_account
                    updated = await update_account(
                        db,
                        existing.account_id,
                        Account(
                            account_id=existing.account_id,
                            email=existing.email,
                            password=password,  # Новый пароль
                            enabled=enabled,
                            metadata=existing.metadata,
                            created_at=existing.created_at,
                            updated_at=existing.updated_at,
                            last_monitored_at=existing.last_monitored_at
                        )
                    )
                    await db.commit()
                    logger.info("✅ Пароль обновлен!")
                    return updated
                else:
                    logger.info("Отменено.")
                    return existing
            
            # Проверяем, существует ли аккаунт с таким account_id
            existing_by_id = await accounts.get_account_by_id(db, account_id)
            if existing_by_id:
                logger.error(f"❌ Аккаунт с ID {account_id} уже существует!")
                logger.error(f"   Email: {existing_by_id.email}")
                return None
            
            # Создаем новый аккаунт
            account_create = AccountCreate(
                account_id=account_id,
                email=email,
                password=password,
                enabled=enabled,
                metadata={}
            )
            
            new_account = await accounts.create_account(db, account_create)
            await db.commit()
            
            logger.info("✅ Аккаунт успешно добавлен в БД!")
            logger.info(f"   Account ID: {new_account.account_id}")
            logger.info(f"   Email: {new_account.email}")
            logger.info(f"   Enabled: {new_account.enabled}")
            logger.info("")
            logger.info("=" * 60)
            logger.info("Аккаунт будет использоваться мониторами при следующем запуске")
            logger.info("=" * 60)
            
            return new_account
            
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении аккаунта: {e}", exc_info=True)
        return None


async def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Добавить аккаунт Thumbtack в базу данных',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Добавить новый аккаунт
  python add_account.py --email user@example.com --password mypassword

  # Добавить аккаунт с указанием ID
  python add_account.py --email user@example.com --password mypassword --account-id my_account

  # Добавить отключенный аккаунт
  python add_account.py --email user@example.com --password mypassword --disabled

  # Обновить пароль существующего аккаунта (интерактивно)
  python add_account.py --email user@example.com --password newpassword --update-password
        """
    )
    
    parser.add_argument('--email', type=str, required=True,
                       help='Email аккаунта Thumbtack')
    parser.add_argument('--password', type=str, required=True,
                       help='Пароль аккаунта Thumbtack')
    parser.add_argument('--account-id', type=str, default=None,
                       help='ID аккаунта (по умолчанию: часть email до @)')
    parser.add_argument('--disabled', action='store_true',
                       help='Добавить аккаунт как отключенный (по умолчанию: enabled=True)')
    parser.add_argument('--update-password', action='store_true',
                       help='Обновить пароль если аккаунт уже существует (без подтверждения)')
    
    args = parser.parse_args()
    
    # Добавляем аккаунт
    account = await add_account(
        email=args.email,
        password=args.password,
        account_id=args.account_id,
        enabled=not args.disabled,
        auto_update_password=args.update_password
    )
    
    if account:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

