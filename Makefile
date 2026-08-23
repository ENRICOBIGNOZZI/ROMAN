.PHONY: install test live shadow sim synthetic-console mc capacity

install:
	pip install -e '.[dev]'

test:
	pytest -q

# Authorized read feeds, path-dependent shadow ledger, no real orders.
live:
	roman-live --capital 10000 --interval 300 --queries-per-source 4 --limit 30

shadow: live

# Explicitly synthetic research harnesses.
sim:
	roman-sim --capital 20000 --days 365 --seed 7

synthetic-console:
	python scripts/run_live_console.py --capital 20000 --ticks 30

mc:
	python scripts/run_monte_carlo.py --capital 20000 --years 250

capacity:
	python scripts/run_capacity.py --years 100
