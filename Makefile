VENV = source venv/bin/activate &&

.PHONY: chrome run once offices install

chrome:
	/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$(HOME)/.chrome-cita" &

run:
	$(VENV) python3 checker.py

once:
	$(VENV) python3 checker.py --once

offices:
	$(VENV) python3 checker.py --list-offices

install:
	python3 -m venv venv
	$(VENV) pip install -r requirements.txt
	$(VENV) playwright install chromium
