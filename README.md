# cita-previa-checker

Automated appointment availability checker for Spanish immigration services (cita previa extranjería).

Currently configured for **POLICÍA TARJETA CONFLICTO UCRANIA** in Barcelona, but can be adapted for other tramites and provinces.

## How it works

Uses Playwright to navigate through the appointment booking flow and checks if slots are available. When found, sends a macOS notification with sound (and optionally Telegram).

**Flow:** Select tramite → Info page → Personal data → Solicitar Cita → Check result

## Setup

```bash
# Install dependencies
make install

# Copy config and fill in your details
cp config.example.py config.py
# Edit config.py with your NIE and name
```

## Usage

```bash
make run       # continuous monitoring
make once      # single check
make offices   # list available offices
```

## Schedule

By default checks at `:03`, `:06`, `:09` past each hour (3 checks/hour).

Configure in `config.py`:

```python
CHECK_MINUTES = [3, 6, 9]
```

## Notifications

- **macOS**: desktop notification + sound alert
- **Telegram** (optional): fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `config.py`

## Adapting for other tramites

1. Run `make once` and look at the tramite dropdown, or inspect the page source
2. Change `TRAMITE_VALUE` in `config.py`
3. Change `BASE_URL` province parameter (`p=8` = Barcelona) for other provinces
