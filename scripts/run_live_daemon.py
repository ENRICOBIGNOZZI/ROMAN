#!/usr/bin/env python3
"""Compatibility launcher for the canonical shadow-live daemon.

All live economic logic lives in ``roman_arb.live.ShadowLiveEngine.run_cycle``;
this file must not maintain a second copy of that pipeline.
"""

from roman_arb.daemon import main


if __name__ == "__main__":
    main()
