#!/usr/bin/env python3
"""
Cita Extranjeria Availability Checker

Checks for appointment availability for POLICÍA TARJETA CONFLICTO UCRANIA
in Barcelona province. Uses Safari via AppleScript — completely undetectable.

Usage:
    python checker.py              # Run continuous checking loop
    python checker.py --once       # Check once and exit
"""

import argparse
import json
import logging
import os
import random
import subprocess
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import urlencode

import config

# --- Logging ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cita-checker")

FOUND_LOG = os.path.join(os.path.dirname(__file__), "found.log")
ENTRY_URL = "https://icp.administracionelectronica.gob.es/icpplus/"
PROVINCE_VALUE = "/icpplustieb/citar?p=8&locale=es"


def log_found(dt: datetime):
    """Append a timestamp to found.log."""
    with open(FOUND_LOG, "a") as f:
        f.write(dt.strftime("%Y-%m-%d %H:%M") + "\n")
    log.info(f"Logged to {FOUND_LOG}")


# --- Notification ---
def notify(title: str, message: str):
    log.info(f"NOTIFICATION: {title} - {message}")
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "Glass"'
    ], capture_output=True)
    subprocess.run(["afplay", "/System/Library/Sounds/Hero.aiff"], capture_output=True)

    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
            data = urlencode({
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": f"{title}\n\n{message}",
            }).encode()
            urlopen(Request(url, data=data, method="POST"), timeout=10)
        except Exception as e:
            log.warning(f"Telegram failed: {e}")


# --- Safari AppleScript helpers ---
def safari_js(js: str) -> str:
    """Execute JavaScript in Safari's current tab."""
    result = subprocess.run(
        ["osascript", "-e",
         f'tell application "Safari" to do JavaScript "{js}" in current tab of window 1'],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        if "Allow JavaScript from Apple Events" in err:
            raise RuntimeError(
                "Safari requires 'Allow JavaScript from Apple Events' enabled. "
                "Go to Safari → Settings → Developer → check the option."
            )
        raise RuntimeError(f"AppleScript error: {err}")
    return result.stdout.strip()


def safari_open(url: str):
    """Navigate Safari to a URL."""
    escaped = url.replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e", f'tell application "Safari" to set URL of document 1 to "{escaped}"'],
        capture_output=True, text=True, timeout=10,
    )


def safari_activate():
    """Bring Safari to front."""
    subprocess.run(
        ["osascript", "-e", 'tell application "Safari" to activate'],
        capture_output=True, timeout=5,
    )


def safari_new_tab():
    """Open a new tab in Safari."""
    subprocess.run(
        ["osascript", "-e",
         'tell application "Safari"\n'
         '  activate\n'
         '  tell window 1 to set current tab to (make new tab with properties {URL:"about:blank"})\n'
         'end tell'],
        capture_output=True, timeout=10,
    )


def safari_close_tab():
    """Close the current Safari tab."""
    subprocess.run(
        ["osascript", "-e", 'tell application "Safari" to close current tab of window 1'],
        capture_output=True, timeout=5,
    )


def safari_get_url() -> str:
    """Get current URL of Safari."""
    result = subprocess.run(
        ["osascript", "-e", 'tell application "Safari" to return URL of document 1'],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip()


def wait_for_page(timeout: float = 15):
    """Wait for Safari page to finish loading."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            state = safari_js("document.readyState")
            if state in ("complete", "interactive"):
                log.debug(f"Page ready: {state}")
                return True
        except Exception as e:
            log.debug(f"wait_for_page: {e}")
        time.sleep(0.5)
    log.warning("wait_for_page timed out")
    return False


def delay(min_s: float = 1.0, max_s: float = 3.0):
    """Human-like random delay."""
    time.sleep(random.uniform(min_s, max_s))


def page_text() -> str:
    """Get visible text from the page body."""
    try:
        return safari_js("document.body.innerText.substring(0, 2000)")
    except Exception:
        return ""


def is_waf_blocked() -> bool:
    """Check if WAF blocked the request."""
    try:
        title = safari_js("document.title")
        url = safari_js("window.location.href")
        log.debug(f"Page: title='{title}' url='{url}'")
        if "Request Rejected" in title:
            log.error(f"WAF blocked! url={url}")
            return True
        return False
    except Exception as e:
        log.debug(f"is_waf_blocked exception: {e}")
        return False


# --- Flow steps ---
def step1_select_province() -> bool:
    log.info("Step 1: Select province...")
    try:
        # Open URL directly in new tab (single step)
        escaped = ENTRY_URL.replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e",
             'tell application "Safari"\n'
             '  activate\n'
             f'  tell window 1 to set current tab to (make new tab with properties {{URL:"{escaped}"}})\n'
             'end tell'],
            capture_output=True, timeout=10,
        )
        time.sleep(3)  # Wait for page to actually start loading
        if not wait_for_page():
            return False
        if is_waf_blocked():
            return False

        # Accept cookies
        try:
            safari_js("document.querySelector(\\\"a[href*='#']\\\")?.click()")
        except Exception:
            pass
        delay(0.3, 0.7)

        # Select Barcelona
        safari_js(f"document.getElementById('form').value = '{PROVINCE_VALUE}'")
        delay(0.3, 0.7)

        # Click Aceptar
        safari_js("document.getElementById('btnAceptar').click()")
        delay(0.5, 1.0)
        wait_for_page()
        return not is_waf_blocked()
    except Exception as e:
        log.error(f"Step 1 failed: {e}")
        return False


def step2_select_tramite() -> bool:
    log.info("Step 2: Select tramite...")
    try:
        delay(0.3, 0.7)

        # Select office
        safari_js(f"document.getElementById('sede').value = '{config.OFFICE_VALUE}'")
        delay(0.3, 0.7)

        # Select tramite
        js = f"document.querySelector('select[name=\\\"tramiteGrupo[0]\\\"]').value = '{config.TRAMITE_VALUE}'"
        safari_js(js)
        delay(0.3, 0.7)

        # Click Aceptar
        safari_js("document.getElementById('btnAceptar').click()")
        delay(0.5, 1.0)
        wait_for_page()
        return not is_waf_blocked()
    except Exception as e:
        log.error(f"Step 2 failed: {e}")
        return False


def step3_click_entrar() -> bool:
    log.info("Step 3: Click Entrar...")
    try:
        delay(0.3, 0.7)
        safari_js("document.getElementById('btnEntrar').click()")
        delay(0.5, 1.0)
        wait_for_page()
        return not is_waf_blocked()
    except Exception as e:
        log.error(f"Step 3 failed: {e}")
        return False


def step4_fill_personal_data() -> bool:
    log.info("Step 4: Fill personal data...")
    try:
        delay(0.3, 0.7)

        # Fill NIE
        safari_js(f"document.getElementById('txtIdCitado').value = '{config.DOC_NUMBER}'")
        delay(0.2, 0.5)

        # Fill name
        safari_js(f"document.getElementById('txtDesCitado').value = '{config.FULL_NAME}'")
        delay(0.2, 0.5)

        # Click Aceptar
        safari_js("document.getElementById('btnEnviar').click()")
        delay(0.5, 1.0)
        wait_for_page()
        return not is_waf_blocked()
    except Exception as e:
        log.error(f"Step 4 failed: {e}")
        return False


def step5_solicitar_cita() -> bool:
    log.info("Step 5: Click Solicitar Cita...")
    try:
        delay(0.3, 0.7)
        safari_js("document.getElementById('btnEnviar').click()")
        delay(0.5, 1.0)
        wait_for_page()
        return not is_waf_blocked()
    except Exception as e:
        log.error(f"Step 5 failed: {e}")
        return False


def check_availability() -> str | None:
    text = page_text().lower()

    for phrase in [
        "en este momento no hay citas disponibles",
        "no hay citas disponibles",
        "no quedan horas disponibles",
    ]:
        if phrase in text:
            return "unavailable"

    for phrase in [
        "selecciona oficina",
        "seleccione una de las siguientes citas disponibles",
        "dispone de 5 minutos",
        "siguiente cita disponible",
        "seleccionar cita",
        "paso 2 de 5",
    ]:
        if phrase in text:
            return "available"

    if "request rejected" in text:
        return None

    return None


def run_check() -> str:
    """Run a single check. Returns: available, unavailable, waf_blocked, error."""
    try:
        if not step1_select_province():
            safari_close_tab()
            return "waf_blocked"

        if not step2_select_tramite():
            safari_close_tab()
            return "waf_blocked"

        if not step3_click_entrar():
            safari_close_tab()
            return "waf_blocked"

        if not config.DOC_NUMBER:
            log.error("DOC_NUMBER not configured")
            safari_close_tab()
            return "error"

        if not step4_fill_personal_data():
            safari_close_tab()
            return "error"

        if not step5_solicitar_cita():
            safari_close_tab()
            return "error"

        result = check_availability()

        if result == "unavailable":
            safari_close_tab()
            return "unavailable"

        if result == "available":
            log_found(datetime.now())
            safari_activate()
            log.info("TAB LEFT OPEN - go complete your appointment!")
            return "available"

        # Unknown state - leave tab open
        text = page_text()
        log.info(f"Unknown page: {text[:300]}")
        return "error"

    except Exception as e:
        log.error(f"Check failed: {e}")
        try:
            safari_close_tab()
        except Exception:
            pass
        return "error"


# --- Schedule ---
def seconds_until_next_check() -> float:
    now = datetime.now()
    for m in config.CHECK_MINUTES:
        if m > now.minute:
            return (m - now.minute) * 60 - now.second + random.uniform(0, 15)
    first_minute = config.CHECK_MINUTES[0]
    return (60 - now.minute + first_minute) * 60 - now.second + random.uniform(0, 15)


def check_safari_js_enabled():
    """Verify Safari allows JavaScript from Apple Events."""
    try:
        safari_js("1+1")
    except RuntimeError as e:
        log.error(str(e))
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description="Cita Extranjeria Availability Checker")
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    args = parser.parse_args()

    check_safari_js_enabled()
    log.info(f"Schedule: check at :{config.CHECK_MINUTES} past each hour")

    check_count = 0
    waf_count = 0

    while True:
        check_count += 1
        log.info(f"=== Check #{check_count} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

        result = run_check()

        if result == "available":
            notify(
                "CITA DISPONIBLE!",
                "Hay citas disponibles para TARJETA CONFLICTO UCRANIA en Barcelona!"
            )
            for _ in range(20):
                time.sleep(30)
                notify("CITA DISPONIBLE!", "Sigue disponible - actua rapido!")
            break

        elif result == "unavailable":
            log.info("No appointments available.")
            waf_count = 0

        elif result == "waf_blocked":
            waf_count += 1
            log.warning(f"WAF blocked (count: {waf_count})")
            if waf_count >= 3:
                backoff = config.WAF_BACKOFF_SECONDS
                log.warning(f"Backing off for {backoff}s...")
                time.sleep(backoff)
                waf_count = 0
                continue

        else:
            log.warning("Could not determine availability.")

        if args.once:
            print(f"\nResult: {result}")
            break

        wait_time = seconds_until_next_check()
        next_str = datetime.fromtimestamp(time.time() + wait_time).strftime("%H:%M:%S")
        log.info(f"Next check at ~{next_str} ({wait_time:.0f}s)")
        time.sleep(wait_time)


if __name__ == "__main__":
    main()
