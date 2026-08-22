.PHONY: install test live mc capacity
install:
	pip install -e '.[dev]'
test:
	pytest -q
live:
	python scripts/run_live.py --capital 20000 --days 365 --seed 7 --verbose
mc:
	python scripts/run_monte_carlo.py --capital 20000 --years 250
capacity:
	python scripts/run_capacity.py --years 100
