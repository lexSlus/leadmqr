import json
import os
import pathlib
from typing import Dict, Any
from playwright.async_api import async_playwright
from playwright_bot.config import SETTINGS
from playwright_bot.state_store import StateStore
from playwright_bot.thumbtack_bot import ThumbTackBot


async def run_continuous_loop():
    """
    Запускает непрерывный цикл обработки лидов с persistent context
    Браузер остается открытым и крутится постоянно!
    """
    import time
    
    store = StateStore(
        path=getattr(SETTINGS, "state_path", ".tt_state.json"),
        cooldown_hours=getattr(SETTINGS, "cooldown_hours", 0)
    )
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        # Используем launch_persistent_context для максимальной скорости
        # Добавляем debug порт для отладки через chrome://inspect
        debug_args = [
            "--remote-debugging-port=9222",
            "--remote-debugging-address=127.0.0.1",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=SETTINGS.user_data_dir,
            headless=False,
            slow_mo=SETTINGS.slow_mo,
            args=debug_args,
            viewport=None,
        )
        
        print("🚀 Запущен persistent context - максимальная скорость!")
        print("🔍 Debug порт: http://localhost:9222")
        print("🌐 Chrome inspect: chrome://inspect")
        print("🔄 Начинаем непрерывный цикл обработки лидов...")
        
        # Создаем новую страницу для работы
        page = await context.new_page()
        
        cycle_count = 0
        
        # БЕСКОНЕЧНЫЙ ЦИКЛ - браузер не закрывается!
        while True:
            try:
                cycle_count += 1
                print(f"\n🔄 === ЦИКЛ #{cycle_count} ===")
                
                # IP check (debug) - только в первом цикле
                if cycle_count == 1:
                    ip_page = await context.new_page()
                    await ip_page.goto("https://api.ipify.org?format=text", wait_until="domcontentloaded", timeout=20000)
                    ip_txt = await ip_page.text_content("body") or ""
                    await ip_page.close()
                    print(f"🌐 IP адрес: {ip_txt}")
                    print("PROFILE USED:", SETTINGS.user_data_dir, "exists:", os.path.isdir(SETTINGS.user_data_dir))

                # Переходим на Thumbtack
                await page.goto("https://www.thumbtack.com/pro-inbox/", wait_until="domcontentloaded")
                print("AFTER GOTO:", page.url)

                bot = ThumbTackBot(page)
                
                # Используем asyncio.run для async методов
                import asyncio
                
                await bot.open_leads()

                leads = await bot.list_new_leads()
                print(f"[DEBUG] found leads: {len(leads)}")

                if not leads:
                    print("ℹ️ Лидов не найдено, ждем следующий цикл...")
                    await asyncio.sleep(60)  # Пауза 1 минута если лидов нет
                    continue

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

                # Извлекаем телефоны
                phones = await bot.extract_phones_from_all_threads()
                
                # Отправляем найденные телефоны в Celery для AI calls
                ai_calls_enqueued = []
                for phone_data in phones:
                    try:
                        from ai_calls.tasks import enqueue_ai_call
                        
                        # Создаем FoundPhone объект для передачи в Celery
                        from leads.models import FoundPhone
                        phone_obj, created = await asyncio.to_thread(
                            FoundPhone.objects.get_or_create,
                            lead_key=phone_data["lead_key"],
                            phone=phone_data["phone"],
                            defaults={"variables": phone_data["variables"]}
                        )
                        
                        # Отправляем ID объекта в Celery
                        task = enqueue_ai_call.delay(str(phone_obj.id))
                        ai_calls_enqueued.append({
                            "phone": phone_data.get("phone", ""),
                            "task_id": task.id,
                            "status": "enqueued",
                            "phone_obj_id": phone_obj.id
                        })
                        print(f"📞 AI call enqueued for phone: {phone_data.get('phone', 'unknown')} (ID: {phone_obj.id})")
                    except Exception as e:
                        print(f"❌ Failed to enqueue AI call: {e}")
                        ai_calls_enqueued.append({
                            "phone": phone_data.get("phone", ""),
                            "error": str(e),
                            "status": "failed"
                        })
                
                print(f"✅ Цикл #{cycle_count} завершен:")
                print(f"   📋 Лидов обработано: {len(sent)}")
                print(f"   📞 Сообщений найдено: {len(phones)}")
                print(f"   🤖 AI calls отправлено: {len(ai_calls_enqueued)}")
                
            except KeyboardInterrupt:
                print("🛑 Получен сигнал остановки...")
                break
            except Exception as e:
                print(f"💥 Ошибка в цикле #{cycle_count}: {e}")
                await asyncio.sleep(60)  # Пауза при ошибке
            
            # Пауза между циклами (5 минут)
            print("⏳ Пауза 5 минут до следующего цикла...")
            await asyncio.sleep(300)