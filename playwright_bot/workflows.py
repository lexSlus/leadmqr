import asyncio
import json
import os
import pathlib
from typing import Dict, Any
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.state_store import StateStore
from playwright_bot.thumbtack_bot import ThumbTackBot


async def run_single_pass() -> Dict[str, Any]:
    store = StateStore(
        path=getattr(SETTINGS, "state_path", ".tt_state.json"),
        cooldown_hours=getattr(SETTINGS, "cooldown_hours", 0)
    )
    async with async_playwright() as pw:

        context = await pw.chromium.launch_persistent_context(
            user_data_dir=SETTINGS.user_data_dir,
            headless=False,  # GUI режим для прохождения капчи
            slow_mo=0,  # Без задержек
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-features=VizDisplayCompositor",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-plugins",
                "--remote-debugging-port=9222",
            ],
            viewport=None,
        )

        page = await context.new_page()

        cycle_count = 0
        while True:
            try:
                cycle_count += 1

                bot = ThumbTackBot(page)
                
                # Автоматический логин если нужно
                await bot.login_if_needed()
                
                await bot.open_leads()
                print("AFTER GOTO:", page.url)
                leads = await bot.list_new_leads()
                print(f"[DEBUG] found leads: {len(leads)}")

                if not leads:
                    print("Лидов не найдено, мгновенная проверка...")
                    await asyncio.sleep(0.1)  # Минимальная пауза 0.1 секунды
                    continue

                # Обрабатываем лиды
                sent = []
                for lead in leads:
                    try:
                        await bot.open_lead_details(lead)
                        lead_key = lead["lead_key"]
                        variables = {
                            "lead_id": lead_key,
                            "lead_url": f"{SETTINGS.base_url}{lead['href']}",
                            "name": lead.get("name") or "",
                            "category": lead.get("category") or "",
                            "location": lead.get("location") or "",
                            "source": "thumbtack",
                        }
                        
                        await bot.send_template_message(dry_run=True)
                        sent.append({
                            "index": lead["index"],
                            "status": "sent",
                            "lead_key": lead_key,
                            "variables": variables,
                        })
                    except Exception as e:
                        sent.append({"index": lead["index"], "status": f"error: {e}"})
                    finally:
                        await bot.open_leads()

                # Только после обработки лидов извлекаем телефоны
                phones = await bot.extract_phones_from_all_threads()
                print(f"📞 Результат извлечения телефонов: {phones}")
                
                # Если есть телефоны - возвращаем их
                if phones:
                    return {
                        "ok": True,
                        "phones": phones,
                        "sent": []
                    }
                
                # Если телефонов нет - продолжаем цикл
                print("Телефонов не найдено, продолжаем...")
                await asyncio.sleep(0.1)  # Минимальная пауза
            except KeyboardInterrupt:
                print("Получен сигнал остановки...")
                break
            except Exception as e:
                print(f"Ошибка в цикле #{cycle_count}: {e}")
                await asyncio.sleep(10)  # Пауза при ошибке
        
        # Браузер закроется только при KeyboardInterrupt
        return {
            "ok": True,
            "message": "Persistent browser stopped",
            "phones": [],  # Добавляем пустые списки для совместимости с таской
            "sent": []
        }