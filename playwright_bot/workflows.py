import asyncio
import json
import os
import pathlib
import time
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
            headless=True,  # Headless режим для Docker
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
                "--lang=en-US",
                "--accept-lang=en-US,en;q=0.9",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor,TranslateUI",
            ],
            viewport=None,
        )

        page = await context.new_page()

        cycle_count = 0
        start_time = time.time()
        max_runtime = 300  # 5 минут максимум
        while time.time() - start_time < max_runtime:
            try:
                cycle_count += 1

                bot = ThumbTackBot(page)
                
                # Автоматический логин если нужно
                await bot.login_if_needed()
                
                await bot.open_leads()
                print("AFTER GOTO:", page.url)
                leads = await bot.list_new_leads()
                print(f"[DEBUG] found leads: {len(leads)}")
                print(f"[DEBUG] cycle #{cycle_count}, runtime: {time.time() - start_time:.1f}s")

                if not leads:
                    print("Лидов не найдено, мгновенная проверка...")
                    await asyncio.sleep(SETTINGS.poll_interval_sec)  # Используем настройку из конфига
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
                        
                        await bot.send_template_message(dry_run=True)  # Тестовый режим
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
                
                # Если есть телефоны - возвращаем их вместе с sent данными
                if phones:
                    return {
                        "ok": True,
                        "phones": phones,
                        "sent": sent  # Не теряем информацию об отправленных сообщениях
                    }
                
                # Если телефонов нет - продолжаем цикл
                print("Телефонов не найдено, продолжаем...")
                await asyncio.sleep(SETTINGS.poll_interval_sec)  # Используем настройку из конфига
            except KeyboardInterrupt:
                print("Получен сигнал остановки...")
                break
            except Exception as e:
                print(f"Ошибка в цикле #{cycle_count}: {e}")
                await asyncio.sleep(10)  # Пауза при ошибке
        
        # Браузер закроется при таймауте или KeyboardInterrupt
        return {
            "ok": True,
            "message": f"Session completed after {time.time() - start_time:.1f}s, {cycle_count} cycles",
            "phones": [],  # Добавляем пустые списки для совместимости с таской
            "sent": []
        }