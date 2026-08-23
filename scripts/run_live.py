#!/usr/bin/env python3
"""Compatibility wrapper for the real shadow/live daemon.

For synthetic Monte Carlo use ``roman-sim`` or ``scripts/run_live_console.py``.
"""
from roman_arb.daemon import main


if __name__ == "__main__":
    main()
