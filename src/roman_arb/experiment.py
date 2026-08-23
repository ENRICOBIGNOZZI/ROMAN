from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: str | Path) -> str:
    p=Path(path)
    if not p.exists(): return "missing"
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def git_commit() -> str:
    try: return subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except Exception: return "unknown"


def archive_state(paths: list[str], archive_root: str="data/archive") -> str:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); out=Path(archive_root)/stamp; out.mkdir(parents=True,exist_ok=True)
    for raw in paths:
        p=Path(raw)
        if p.exists(): shutil.move(str(p),str(out/p.name))
        for suffix in ('-wal','-shm'):
            q=Path(str(p)+suffix)
            if q.exists(): shutil.move(str(q),str(out/q.name))
    return str(out)


def write_manifest(out_path: str, capital: float, hours: float, snapshot_db: str, tracking_db: str,
                   sources: list[str] | None=None, config_path: str | None=None, fx_path: str='data/fx_rates.json') -> dict:
    from .config import default_config_path
    config=str(config_path or default_config_path())
    payload={
        'experiment':'ROMAN shadow forward validation','paper_only':True,'started_at':datetime.now(timezone.utc).isoformat(),
        'planned_hours':float(hours),'capital_eur':float(capital),'git_commit':git_commit(),'python':platform.python_version(),
        'config_path':config,'config_sha256':_sha256(config),'fx_path':fx_path,'fx_sha256':_sha256(fx_path),
        'snapshot_db':snapshot_db,'tracking_db':tracking_db,'sources':sources or 'registry-default',
        # Must match scripts/run_live_daemon.py and PosteriorFDRSelector. A manifest
        # that records 0.05 while the process actually ran at 0.25 is not an audit.
        'fdr_alpha':float(os.getenv('ROMAN_FDR_ALPHA','0.25')),'fx_friction':float(os.getenv('ROMAN_FX_FRICTION','0.004')),
        'credential_presence':{k:bool(os.getenv(k)) for k in ('EBAY_CLIENT_ID','EBAY_CLIENT_SECRET','STOCKX_API_KEY','STOCKX_ACCESS_TOKEN','REVERB_TOKEN','ETSY_API_KEY','ETSY_OAUTH_TOKEN','MELI_ACCESS_TOKEN','RAKUTEN_APPLICATION_ID','RAKUTEN_ACCESS_KEY')},
        'warning':'No secret values are recorded. Shadow positions assume paper fills and do not submit orders.'
    }
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2,ensure_ascii=False)); return payload
