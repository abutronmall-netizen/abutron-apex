.PHONY: help install test backtest dashboard sweep clean

help:
	@echo "make install    - install python deps"
	@echo "make test       - run the test suite"
	@echo "make backtest   - walk-forward backtest -> results/"
	@echo "make sweep      - multi-seed robustness sweep"
	@echo "make dashboard  - live paper desk on http://localhost:8000"
	@echo "make clean      - remove generated artefacts"

install:
	pip install -r requirements.txt

test:
	python3 -m pytest -q

backtest:
	python3 scripts/run_backtest.py --bars 3200 --out results

sweep:
	python3 scripts/sweep.py --bars 1600 --seeds 5

dashboard:
	python3 scripts/run_server.py

collect:
	python3 scripts/collect.py --once

serve:
	python3 scripts/run_server.py --host 0.0.0.0

ablate:
	python3 scripts/agent_ablation.py

real:
	python3 scripts/run_real.py

snapshot:
	python3 scripts/make_snapshot.py

clean:
	rm -rf results/* state/*.jsonl __pycache__ .pytest_cache
