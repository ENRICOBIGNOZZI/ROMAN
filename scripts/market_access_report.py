#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from roman_arb.feeds import market_access_registry


def source_status(policy) -> str:
    if policy.automated_collection:
        if not policy.credential_env:
            return "READY_PUBLIC"
        return (
            "READY_CREDENTIALS"
            if all(os.getenv(key, "") for key in policy.credential_env)
            else "NEEDS_CREDENTIALS"
        )
    if "existing" in policy.access_mode:
        return "EXISTING_ACCESS_ONLY"
    if "partner" in policy.access_mode or "allowlisted" in policy.access_mode:
        return "PARTNER_REQUIRED"
    return "PERMISSION_REQUIRED"


def build_report() -> list[dict]:
    out = []
    for key, policy in sorted(market_access_registry().items()):
        out.append(
            {
                "source": key,
                "domain": policy.domain,
                "access_mode": policy.access_mode,
                "status": source_status(policy),
                "data_role": policy.data_role,
                "credential_env": list(policy.credential_env),
                "notes": policy.notes,
            }
        )
    return out


def main():
    rows = build_report()
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
