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
import random
import subprocess
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import Stealth

import config

# Initialize stealth with Spanish locale settings
stealth = Stealth(
    navigator_languages_override=("es-ES", "es"),
    navigator_platform_override="MacIntel",
)

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cita-checker")


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
async def create_browser_context(playwright) -> tuple:
    """Create a stealth browser context."""
    browser = await playwright.chromium.launch(
        headless=False,  # Headed mode is less likely to be detected
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )

    context = await browser.new_context(
        viewport={"width": random.randint(1200, 1400), "height": random.randint(800, 1000)},
        locale="es-ES",
        timezone_id="Europe/Madrid",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{random.choice(['120', '121', '122', '123', '124', '125'])}.0.0.0 Safari/537.36"
        ),
    )

    return browser, context


# --- Page flow ---
async def step1_load_page(page: Page) -> bool:
    """Navigate to the initial page."""
    log.info("Step 1: Loading cita previa page...")
    try:
        await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await human_delay(2, 4)

        # Check for WAF block
        if "Request Rejected" in (await page.content()):
            log.error("WAF blocked us on initial page load!")
            return False

        # Verify we're on the right page
        title = await page.title()
        if "cita previa" not in title.lower() and "solicitud" not in title.lower():
            log.warning(f"Unexpected page title: {title}")

        return True
    except Exception as e:
        log.error(f"Failed to load page: {e}")
        return False


async def step2_select_tramite(page: Page) -> bool:
    """Select the office and tramite, then click Aceptar."""
    log.info("Step 2: Selecting office and tramite...")
    try:
        # Accept cookies if banner is present
        try:
            cookie_btn = page.locator("a:has-text('Acepto')")
            if await cookie_btn.is_visible(timeout=2000):
                await cookie_btn.click()
                await human_delay(0.5, 1.0)
        except Exception:
            pass

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

        # Check for WAF
        content = await page.content()
        if "Request Rejected" in content:
            log.error("WAF blocked us after selecting tramite!")
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

        content = await page.content()
        if "Request Rejected" in content:
            log.error("WAF blocked us after clicking Entrar!")
            return False

        return True
    except Exception as e:
        log.error(f"Failed to click Entrar: {e}")
        return False


async def step4_fill_personal_data(page: Page) -> bool:
    """Fill in personal data form."""
    log.info("Step 4: Filling personal data...")
    try:
        await human_delay(1, 2)

        # For this tramite, only NIE is available (already selected)
        # Fill NIE number
        await slow_type(page, "#txtIdCitado", config.DOC_NUMBER)
        await human_delay(0.5, 1)

        # Fill name
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

        # Click Aceptar (on this page it's #btnEnviar)
        await page.click("#btnEnviar")
        await human_delay(2, 4)

        content = await page.content()
        if "Request Rejected" in content:
            log.error("WAF blocked us after personal data!")
            return False

        return True
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

        content = await page.content()
        if "Request Rejected" in content:
            log.error("WAF blocked us after Solicitar Cita!")
            return False

        return True
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
        "seleccione una de las siguientes citas disponibles",
        "dispone de 5 minutos",
        "siguiente cita disponible",
        "seleccionar cita",
        "paso 2 de 5",  # If we reach step 2, it means offices are available
    ]
    for phrase in available_phrases:
        if phrase in text_lower:
            return "available"

    # WAF block
    if "request rejected" in text_lower:
        return None

    return None


async def run_check(playwright) -> str:
    """
    Run a single availability check through the full flow.
    Returns: "available", "unavailable", "waf_blocked", or "error"
    """
    browser, context = await create_browser_context(playwright)

    try:
        page = await context.new_page()
        await stealth.apply_stealth_async(page)

        # Flow verified manually on the live site:
        # Page 1: Select tramite (btnAceptar)
        # Page 2: Info page (btnEntrar)
        # Page 3: Personal data - NIE + name (btnEnviar)
        # Page 4: Action selection - "Solicitar Cita" (btnEnviar)
        # Page 5: Result - shows availability or "no hay citas disponibles"

        # Step 1: Load initial page
        if not await step1_load_page(page):
            return "waf_blocked"

        # Step 2: Select tramite + click Aceptar
        if not await step2_select_tramite(page):
            return "waf_blocked"

        # Step 3: Click Entrar on info page
        if not await step3_click_entrar(page):
            return "waf_blocked"

        # Step 4: Fill personal data (NIE + name required)
        if not config.DOC_NUMBER:
            log.error("DOC_NUMBER not configured in config.py - cannot proceed past info page")
            return "error"

        if not await step4_fill_personal_data(page):
            return "error"

        # Step 5: Click "Solicitar Cita"
        if not await step5_solicitar_cita(page):
            return "error"

        # Now check result page for availability
        result = await check_availability(page)
        if result:
            if result == "available":
                # Save screenshot as proof
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"/tmp/cita_AVAILABLE_{ts}.png")
            return result

        # Unknown page state - save screenshot for debugging
        text = await page.inner_text("body")
        log.info(f"Page text (first 500 chars): {text[:500]}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=f"/tmp/cita_unknown_{ts}.png")
        log.info(f"Screenshot saved: /tmp/cita_unknown_{ts}.png")
        return "error"

    except Exception as e:
        log.error(f"Check failed with exception: {e}")
        return "error"
    finally:
        await browser.close()


async def list_offices(playwright):
    """List available offices for the selected tramite."""
    browser, context = await create_browser_context(playwright)
    try:
        page = await context.new_page()
        await stealth.apply_stealth_async(page)

        await page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await human_delay(2, 3)

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
        await browser.close()


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
        log.info(f"Hot window: {days[hw['day']]} {hw['hour']:02d}:00 -> every {hw['interval']}s")

    async with async_playwright() as playwright:
        if args.list_offices:
            await list_offices(playwright)
            return

        check_count = 0
        waf_count = 0

        while True:
            check_count += 1
            log.info(f"=== Check #{check_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

            result = await run_check(playwright)

            if result == "available":
                notify(
                    "CITA DISPONIBLE!",
                    "Hay citas disponibles para POLICÍA TARJETA CONFLICTO UCRANIA en Barcelona! "
                    "Ve a la web AHORA!"
                )
                for _ in range(10):
                    await asyncio.sleep(30)
                    notify("CITA DISPONIBLE!", "Sigue disponible - actua rapido!")

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

            if args.once:
                print(f"\nResult: {result}")
                break

            # Decide wait time: hot window vs normal schedule
            hw = get_hot_window()
            if hw:
                wait_time = hw["interval"] + random.uniform(0, 10)
                log.info(f"HOT WINDOW active -> next check in {wait_time:.0f}s")
            else:
                wait_time = seconds_until_next_check()
                next_time = datetime.now().timestamp() + wait_time
                next_str = datetime.fromtimestamp(next_time).strftime("%H:%M:%S")
                log.info(f"Next check at ~{next_str} ({wait_time:.0f}s)")

            await asyncio.sleep(wait_time)


if __name__ == "__main__":
    asyncio.run(main())
