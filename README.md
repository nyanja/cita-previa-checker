# cita-previa-checker

Automated appointment availability checker for Spanish immigration services (cita previa extranjería).

Currently configured for **POLICÍA TARJETA CONFLICTO UCRANIA** in Barcelona, but can be adapted for other tramites and provinces.

## How it works

Uses Safari via AppleScript to navigate through the appointment booking flow — completely undetectable by the site's WAF. When appointments are found, sends a macOS notification with sound (and optionally Telegram) and leaves the tab open so you can complete the booking.

**Flow:** Select province → Select tramite → Info page → Personal data → Solicitar Cita → Check result

## Requirements

- macOS with Safari
- Safari → Settings → Developer → **Allow JavaScript from Apple Events** (must be enabled)
- Python 3 (no external dependencies)

## Setup

```bash
# Create venv
make install

# Copy config and fill in your details
cp config.example.py config.py
# Edit config.py with your NIE and name
```

## Usage

```bash
make run       # continuous monitoring
make once      # single check
```

## Schedule

By default checks at `:01`, `:03`, `:06`, `:15`, `:30`, `:45` past each hour.

Configure in `config.py`:

```python
CHECK_MINUTES = [1, 3, 6, 15, 30, 45]
```

## Notifications

- **macOS**: desktop notification + sound alert (always enabled)
- **Telegram** (optional): fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `config.py`

## Adapting for other tramites

1. Change `TRAMITE_VALUE` in `config.py` (inspect the tramite dropdown on the site)
2. Change `PROVINCE_VALUE` in `checker.py` for other provinces (`p=8` = Barcelona)
