#!/usr/bin/env python3
"""
Cita Extranjeria Availability Checker

Checks for appointment availability for POLICÍA TARJETA CONFLICTO UCRANIA
in Barcelona province. Uses Playwright with stealth to avoid WAF detection.

Usage:
    python checker.py              # Run continuous checking loop
    python checker.py --once       # Check once and exit
    python checker.py --list-offices  # List available offices
"""

import argparse
import asyncio
import logging
import os
import random
import subprocess
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Page, BrowserContext

import config

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cita-checker")


FOUND_LOG = os.path.join(os.path.dirname(__file__), "found.log")


def log_found(dt: datetime):
    """Append a timestamp to found.log when appointments are detected."""
    line = dt.strftime("%Y-%m-%d %H:%M") + "\n"
    with open(FOUND_LOG, "a") as f:
        f.write(line)
    log.info(f"Logged to {FOUND_LOG}")


# --- Notification ---
def notify(title: str, message: str):
    """Send macOS notification with sound + optional Telegram."""
    log.info(f"🔔 NOTIFICATION: {title} - {message}")

    # macOS notification
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "Glass"'
    ], capture_output=True)

    # Also play a loud alert sound
    subprocess.run(["afplay", "/System/Library/Sounds/Hero.aiff"], capture_output=True)

    # Telegram notification
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
            data = urlencode({
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": f"🚨 {title}\n\n{message}",
                "parse_mode": "HTML",
            }).encode()
            req = Request(url, data=data, method="POST")
            urlopen(req, timeout=10)
            log.info("Telegram notification sent")
        except Exception as e:
            log.warning(f"Telegram notification failed: {e}")


def notify_error(message: str):
    """Send error notification (less intrusive)."""
    log.warning(f"⚠️ {message}")


# --- Human-like delays ---
async def human_delay(min_s: float = 1.0, max_s: float = 3.0):
    """Wait a random human-like amount of time."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def slow_type(page: Page, selector: str, text: str):
    """Type text character by character with random delays."""
    await page.click(selector)
    await human_delay(0.3, 0.7)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(50, 150))
    await human_delay(0.2, 0.5)


# --- Browser setup ---
CDP_PORT = 9222


async def create_browser_context(playwright) -> tuple:
    """Connect to real Chrome via CDP. Chrome must be running with --remote-debugging-port."""
    try:
        browser = await playwright.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    except Exception:
        log.error(
            f"Cannot connect to Chrome on port {CDP_PORT}. Start Chrome with:\n"
            f'  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port={CDP_PORT}'
        )
        raise

    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    return browser, context


# --- Page flow ---
ENTRY_URL = "https://icp.administracionelectronica.gob.es/icpplus/"
PROVINCE_VALUE = "/icpplustieb/citar?p=8&locale=es"  # Barcelona


async def check_waf(page: Page) -> bool:
    """Return True if WAF blocked us."""
    if "Request Rejected" in (await page.content()):
        log.error("WAF blocked!")
        return True
    return False


async def step1_select_province(page: Page) -> bool:
    """Go to the generic entry page and select Barcelona province."""
    log.info("Step 1: Loading province selection page...")
    try:
        await page.evaluate(f'window.location.href = "{ENTRY_URL}"')
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
        await human_delay(2, 4)

        if await check_waf(page):
            return False

        # Accept cookies if present
        try:
            cookie_btn = page.locator("a:has-text('Acepto')")
            if await cookie_btn.is_visible(timeout=2000):
                await cookie_btn.click()
                await human_delay(0.5, 1.0)
        except Exception:
            pass

        # Select Barcelona from province dropdown
        await human_delay(1, 2)
        province_select = page.locator("#form")
        await province_select.select_option(value=PROVINCE_VALUE)
        await human_delay(1.5, 3)

        # Click Aceptar
        await page.click("#btnAceptar")
        await human_delay(2, 4)

        if await check_waf(page):
            return False

        return True
    except Exception as e:
        log.error(f"Failed to select province: {e}")
        return False


async def step2_select_tramite(page: Page) -> bool:
    """Select the office and tramite, then click Aceptar."""
    log.info("Step 2: Selecting office and tramite...")
    try:
        # Select office
        await human_delay(1, 2)
        office_select = page.locator("#sede")
        await office_select.select_option(value=config.OFFICE_VALUE)
        await human_delay(1.5, 3)

        # Select tramite
        tramite_select = page.locator('select[name="tramiteGrupo[0]"]')
        await tramite_select.select_option(value=config.TRAMITE_VALUE)
        await human_delay(1.5, 3)

        # Click Aceptar
        await page.click("#btnAceptar")
        await human_delay(2, 4)

        if await check_waf(page):
            return False

        return True
    except Exception as e:
        log.error(f"Failed to select tramite: {e}")
        return False


async def step3_click_entrar(page: Page) -> bool:
    """Click 'Entrar' on the information page."""
    log.info("Step 3: Clicking Entrar...")
    try:
        await page.wait_for_selector("#btnEntrar", timeout=10000)
        await human_delay(1.5, 3)
        await page.click("#btnEntrar")
        await human_delay(2, 4)
        return not await check_waf(page)
    except Exception as e:
        log.error(f"Failed to click Entrar: {e}")
        return False


async def step4_fill_personal_data(page: Page) -> bool:
    """Fill in personal data form."""
    log.info("Step 4: Filling personal data...")
    try:
        await human_delay(1, 2)

        # For this tramite, only NIE is available (already selected)
        await slow_type(page, "#txtIdCitado", config.DOC_NUMBER)
        await human_delay(0.5, 1)

        await slow_type(page, "#txtDesCitado", config.FULL_NAME)
        await human_delay(0.5, 1)

        # Select country if dropdown exists (not on all tramites)
        try:
            country_select = page.locator("#txtPaisNac")
            if await country_select.is_visible(timeout=2000):
                await country_select.select_option(label=config.COUNTRY)
                await human_delay(0.5, 1)
        except Exception:
            pass

        await page.click("#btnEnviar")
        await human_delay(2, 4)
        return not await check_waf(page)
    except Exception as e:
        log.error(f"Failed to fill personal data: {e}")
        return False


async def step5_solicitar_cita(page: Page) -> bool:
    """Click 'Solicitar Cita' button (#btnEnviar on the action selection page)."""
    log.info("Step 5: Clicking Solicitar Cita...")
    try:
        await page.wait_for_selector("#btnEnviar", timeout=10000)
        await human_delay(1, 2)
        await page.click("#btnEnviar")
        await human_delay(2, 4)
        return not await check_waf(page)
    except Exception as e:
        log.error(f"Failed to click Solicitar Cita: {e}")
        return False


async def check_availability(page: Page) -> str | None:
    """
    Check the current page for availability indicators.
    Returns:
        "available" - appointments are available
        "unavailable" - no appointments right now
        None - couldn't determine (error/unexpected page)
    """
    content = await page.content()
    text = await page.inner_text("body")
    text_lower = text.lower()

    # No appointments available
    no_cita_phrases = [
        "en este momento no hay citas disponibles",
        "no hay citas disponibles",
        "no quedan horas disponibles",
    ]
    for phrase in no_cita_phrases:
        if phrase in text_lower:
            return "unavailable"

    # Appointments ARE available
    available_phrases = [
        "selecciona oficina",  # Office selection = appointments exist
        "seleccione una de las siguientes citas disponibles",
        "dispone de 5 minutos",
        "siguiente cita disponible",
        "seleccionar cita",
        "paso 2 de 5",
    ]
    for phrase in available_phrases:
        if phrase in text_lower:
            return "available"

    # WAF block
    if "request rejected" in text_lower:
        return None

    return None


async def run_check(playwright) -> tuple[str, object]:
    """
    Run a single availability check through the full flow.
    Returns: (result, browser) where result is "available", "unavailable", "waf_blocked", or "error"
    Browser is returned open when result != "unavailable" so user can interact.
    """
    browser, context = await create_browser_context(playwright)
    page = await context.new_page()

    try:


        # Flow: all button clicks, no direct URL navigation after entry
        # 1. /icpplus/ -> select Barcelona -> Aceptar
        # 2. Select tramite -> Aceptar
        # 3. Info page -> Entrar
        # 4. Personal data -> Aceptar
        # 5. Solicitar Cita -> result

        # Step 1: Select province (Barcelona)
        if not await step1_select_province(page):
            await page.close()
            return "waf_blocked", None

        # Step 2: Select tramite + click Aceptar
        if not await step2_select_tramite(page):
            await page.close()
            return "waf_blocked", None

        # Step 3: Click Entrar on info page
        if not await step3_click_entrar(page):
            await page.close()
            return "waf_blocked", None

        # Step 4: Fill personal data (NIE + name required)
        if not config.DOC_NUMBER:
            log.error("DOC_NUMBER not configured in config.py - cannot proceed past info page")
            await page.close()
            return "error", None

        if not await step4_fill_personal_data(page):
            await page.close()
            return "error", None

        # Step 5: Click "Solicitar Cita"
        if not await step5_solicitar_cita(page):
            await page.close()
            return "error", None

        # Now check result page for availability
        result = await check_availability(page)
        if result == "unavailable":
            await page.close()
            return "unavailable", None

        if result == "available":
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            await page.screenshot(path=f"/tmp/cita_AVAILABLE_{ts}.png")
            log_found(datetime.now())
            log.info("PAGE LEFT OPEN - go complete your appointment!")
            return "available", page

        # Unknown page state - keep page open for inspection
        text = await page.inner_text("body")
        log.info(f"Page text (first 500 chars): {text[:500]}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=f"/tmp/cita_unknown_{ts}.png")
        log.info(f"Screenshot saved: /tmp/cita_unknown_{ts}.png")
        log.info("PAGE LEFT OPEN for inspection")
        return "error", page

    except Exception as e:
        log.error(f"Check failed with exception: {e}")
        await page.close()
        return "error", None


async def list_offices(playwright):
    """List available offices for the selected tramite."""
    browser, context = await create_browser_context(playwright)
    try:
        page = await context.new_page()


        await step1_select_province(page)
        await human_delay(1, 2)

        offices = await page.eval_on_selector_all(
            "#sede option",
            "options => options.map(o => ({value: o.value, text: o.textContent.trim()}))"
        )

        print("\nAvailable offices:")
        print("-" * 80)
        for o in offices:
            print(f"  Value: {o['value']:4s}  |  {o['text']}")
        print("-" * 80)
    finally:
        await page.close()


def get_hot_window() -> dict | None:
    """Check if we're currently in a hot window."""
    now = datetime.now()
    for hw in config.HOT_WINDOWS:
        if now.weekday() == hw["day"] and now.hour == hw["hour"]:
            return hw
    return None


def seconds_until_next_check() -> float:
    """Calculate seconds until the next scheduled check minute."""
    now = datetime.now()
    current_minute = now.minute
    current_second = now.second

    # Find next check minute this hour or next hour
    for m in config.CHECK_MINUTES:
        if m > current_minute or (m == current_minute and current_second < 30):
            return (m - current_minute) * 60 - current_second + random.uniform(0, 15)

    # All check minutes passed this hour — wait for first minute next hour
    first_minute = config.CHECK_MINUTES[0]
    return (60 - current_minute + first_minute) * 60 - current_second + random.uniform(0, 15)


async def main():
    parser = argparse.ArgumentParser(description="Cita Extranjeria Availability Checker")
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    parser.add_argument("--list-offices", action="store_true", help="List available offices")
    args = parser.parse_args()

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    log.info(f"Schedule: check at :{config.CHECK_MINUTES} past each hour")
    for hw in config.HOT_WINDOWS:
        log.info(f"Hot window: {days[hw['day']]} {hw['hour']:02d}:00")

    async with async_playwright() as playwright:
        if args.list_offices:
            await list_offices(playwright)
            return

        check_count = 0
        waf_count = 0

        while True:
            check_count += 1
            log.info(f"=== Check #{check_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

            result, open_page = await run_check(playwright)

            if result == "available":
                notify(
                    "CITA DISPONIBLE!",
                    "Hay citas disponibles para POLICÍA TARJETA CONFLICTO UCRANIA en Barcelona! "
                    "Ve a la web AHORA!"
                )
                # Keep alerting while page is open for user to act
                for _ in range(20):
                    await asyncio.sleep(30)
                    notify("CITA DISPONIBLE!", "Sigue disponible - actua rapido!")
                break

            elif result == "unavailable":
                log.info("No appointments available right now.")
                waf_count = 0

            elif result == "waf_blocked":
                waf_count += 1
                log.warning(f"WAF blocked (count: {waf_count})")
                if waf_count >= 3:
                    backoff = config.WAF_BACKOFF_SECONDS
                    log.warning(f"Too many WAF blocks. Backing off for {backoff}s...")
                    notify_error(f"WAF blocked {waf_count} times. Backing off {backoff}s.")
                    await asyncio.sleep(backoff)
                    waf_count = 0
                    continue

            else:
                log.warning("Could not determine availability status.")
                # Page left open for inspection — wait for user to close it
                if open_page:
                    log.info("Page left open for inspection. Close the tab to continue.")
                    try:
                        while not open_page.is_closed():
                            await asyncio.sleep(1)
                    except Exception:
                        pass

            if args.once:
                print(f"\nResult: {result}")
                break

            # Wait until next scheduled check
            wait_time = seconds_until_next_check()
            next_time = datetime.now().timestamp() + wait_time
            next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
            log.info(f"Next check at ~{next_str} ({wait_time:.0f}s)")

            await asyncio.sleep(wait_time)


if __name__ == "__main__":
    asyncio.run(main())
