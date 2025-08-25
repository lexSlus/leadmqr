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
        # browser = await pw.chromium.launch(
        #     headless=False,
        #     slow_mo=getattr(SETTINGS, "slow_mo", 0),
        #     args=getattr(SETTINGS, "chromium_args", []),
        # )
        # state_path = Path(SETTINGS.state_path)
        # context = await browser.new_context(
        #     storage_state=str(state_path) if state_path.exists() else None,
        #     viewport=None,
        # )
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=SETTINGS.user_data_dir,
            headless=False,
            slow_mo=SETTINGS.slow_mo,
            args=getattr(SETTINGS, "chromium_args", ["--no-sandbox"]),
            viewport=None,
        )
        try:
            p = await context.new_page()
            await p.goto("https://api.ipify.org?format=text", wait_until="domcontentloaded", timeout=20000)
            ip_txt = (await p.text_content("body")) or ""
            await p.close()
        except Exception as e:
            print("[DEBUG] IP check failed:", e)
        # --- end DEBUG ---
        print("PROFILE USED:", SETTINGS.user_data_dir, "exists:", os.path.isdir(SETTINGS.user_data_dir))
        try:
            state = await context.storage_state()
            pathlib.Path("/app/debug").mkdir(parents=True, exist_ok=True)
            with open("/app/debug/cookies.json", "w") as f:
                json.dump(state.get("cookies", []), f, indent=2)
        except Exception as e:
            print("state dump err:", e)

        page = await context.new_page()
        await page.goto("https://www.thumbtack.com/pro-inbox/", wait_until="domcontentloaded")
        # await page.screenshot(path="/app/debug/inbox.png", full_page=True)
        print("AFTER GOTO:", page.url)

        bot = ThumbTackBot(page)

        await bot.open_leads()

        leads = await bot.list_new_leads()
        print(f"[DEBUG] found leads: {len(leads)}")

        if not leads:
            return {
                "ok": True,
                "leads_processed": 0,
                "messages_processed": 0,
                "sent": [],
                "phones": [],
                "message": "No leads"
            }
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
                # if store.was_lead_sent(lead_key):
                #     sent.append({"index": lead["index"], "status": "skipped_already_sent", "lead_key": lead_key})
                # else:
                await bot.send_template_message(dry_run=True)
                # store.mark_lead_sent(lead_key)
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

        # phones = await bot.extract_phones_from_all_threads(store=store)
        phones = await bot.extract_phones_from_all_threads()
        # await browser.close()
        return {
            "ok": True,
            "leads_processed": len(sent),
            "messages_processed": len(phones),
            "sent": sent,
            "phones": phones,
            "variables": [s.get("variables") for s in sent if "variables" in s],
        }


# def run_until_leads() -> Dict[str, Any]:
#     """
#     Крутимся, пока не найдём хотя бы один лид:
#       - опрашиваем /pro-leads каждые SETTINGS.poll_interval_sec
#       - каждые 3 часа перезапускаем браузер
#     """
#     start_time = time.time()
#     store = StateStore(
#         path=getattr(SETTINGS, "state_path", ".tt_state.json"),
#         cooldown_hours=getattr(SETTINGS, "cooldown_hours", 0)  # 0 = никогда не повторять
#     )
#
#     while True:
#         with BrowserManager() as bw:
#             bot = ThumbTackBot(bw.page)
#
#             # ---------- Поллинг лидов ----------
#             while True:
#                 try:
#                     # Рестарт по времени
#                     if time.time() - start_time >= SETTINGS.restart_interval_sec:
#                         start_time = time.time()
#                         break  # выходим во внешний цикл -> рестарт браузера
#
#                     bot.open_leads()
#                     leads = bot.list_new_leads()
#                     if leads:
#                         # ---------- Шаг 1: отправка сообщений по найденным лидам ----------
#                         sent = []
#                         for lead in leads:
#                             try:
#                                 bot.open_lead_details(lead)
#                                 # анти‑спам: проверяем по URL карточки
#                                 lead_url = bot.page.url
#                                 lead_key = bot.lead_key_from_url(lead_url)
#                                 if store.was_lead_sent(lead_key):
#                                     sent.append({"index": lead["index"], "status": "skipped_already_sent"})
#                                 else:
#                                     bot.send_template_message()
#                                     store.mark_lead_sent(lead_key)
#                                     sent.append({"index": lead["index"], "status": "sent"})
#                             except Exception as e:
#                                 sent.append({"index": lead["index"], "status": f"error: {e}"})
#                             finally:
#                                 bot.open_leads()
#
#                         # ---------- Шаг 2: сбор телефонов из Messages ----------
#                         phones = bot.extract_phones_from_all_threads(store=store)
#
#                         return {
#                             "ok": True,
#                             "leads_processed": len(sent),
#                             "messages_processed": len(phones),
#                             "sent": sent,
#                             "phones": phones,
#                         }
#
#                     # нет лидов — ждём и повторяем
#                     time.sleep(SETTINGS.poll_interval_sec)
#
#                 except KeyboardInterrupt:
#                     return {"ok": False, "message": "Stopped by user"}
#                 except Exception:
#                     # на случай временных сбоёв — подождём и продолжим
#                     time.sleep(SETTINGS.poll_interval_sec)



