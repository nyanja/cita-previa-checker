VENV = source venv/bin/activate &&

.PHONY: run once install

run:
	$(VENV) python3 checker.py

once:
	$(VENV) python3 checker.py --once

install:
	python3 -m venv venv
	$(VENV) pip install -r requirements.txt
