VENV = source venv/bin/activate &&

.PHONY: run once offices install

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
