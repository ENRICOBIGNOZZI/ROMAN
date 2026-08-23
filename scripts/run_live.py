#!/usr/bin/env python3
"""Canonical shadow-live launcher.

This script intentionally delegates to the installed live daemon. Synthetic
experiments belong to ``roman-sim`` / ``roman_arb.simulator``.
"""

from roman_arb.daemon import main


if __name__ == "__main__":
    main()
