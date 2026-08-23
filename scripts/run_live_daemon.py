from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from roman_arb.live import ShadowLiveEngine


class State:
    payload={"brand":"Reselling BOT","status":"STARTING","capital":10000,"nav":10000}
    error=""
    lock=threading.Lock()


def handler_factory(state):
    class Handler(BaseHTTPRequestHandler):
        def _send(self,code,body,ctype="application/json; charset=utf-8"):
            self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Cache-Control","no-store,max-age=0"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_OPTIONS(self):
            self.send_response(204); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Methods","GET,OPTIONS"); self.end_headers()
        def do_GET(self):
            path=self.path.split("?",1)[0]
            if path=="/health":
                with state.lock: p={"ok":not bool(state.error),"status":state.payload.get("status"),"error":state.error}
                return self._send(200,json.dumps(p).encode())
            if path in ("/dashboard.json","/api/dashboard","/"):
                with state.lock: p=dict(state.payload)
                return self._send(200,json.dumps(p,ensure_ascii=False).encode())
            self._send(404,b'{"error":"not found"}')
        def log_message(self,*_): return
    return Handler


def main():
    p=argparse.ArgumentParser(description="Reselling BOT paper/shadow live daemon")
    p.add_argument("--capital",type=float,default=10000); p.add_argument("--interval",type=int,default=300); p.add_argument("--queries-per-source",type=int,default=2); p.add_argument("--limit",type=int,default=40); p.add_argument("--health-port",type=int,default=8787)
    p.add_argument("--max-hours",type=float,default=48.0,help="0=until stopped"); p.add_argument("--once",action="store_true"); p.add_argument("--snapshot-db",default="data/roman_snapshots.sqlite"); p.add_argument("--tracking-db",default="data/roman_tracking.sqlite"); p.add_argument("--dashboard",default="outputs/live/dashboard.json")
    args=p.parse_args()
    engine=ShadowLiveEngine(capital=args.capital,snapshot_db=args.snapshot_db,tracking_db=args.tracking_db,dashboard_path=args.dashboard,queries_per_source=args.queries_per_source,rows_per_query=args.limit)
    state=State(); state.payload.update(capital=args.capital,nav=args.capital)
    server=ThreadingHTTPServer(("0.0.0.0",args.health_port),handler_factory(state)); threading.Thread(target=server.serve_forever,daemon=True).start()
    deadline=time.time()+args.max_hours*3600 if args.max_hours>0 else None
    print(f"Reselling BOT shadow-live | capital=EUR {args.capital:.2f} | API http://0.0.0.0:{args.health_port}/dashboard.json",flush=True)
    try:
        while True:
            t0=time.time()
            try:
                payload=engine.run_cycle(); payload["experiment"]["target_hours"]=args.max_hours if args.max_hours>0 else 48.0
                with state.lock: state.payload=payload; state.error=""
                print(json.dumps({"status":payload.get("status"),"rows":payload.get("cycle_rows"),"signals":payload.get("qualified_signals"),"deployed":payload.get("deployed")}),flush=True)
            except Exception as e:
                with state.lock: state.error=str(e)[:500]; state.payload=dict(state.payload,status="ERROR",error=state.error)
                print(f"cycle error: {e}",flush=True)
            if args.once or (deadline is not None and time.time()>=deadline): break
            time.sleep(max(1,args.interval-int(time.time()-t0)))
    finally:
        with state.lock: state.payload=dict(state.payload,status="SHADOW-COMPLETE")
        Path(args.dashboard).parent.mkdir(parents=True,exist_ok=True); Path(args.dashboard).write_text(json.dumps(state.payload,indent=2,ensure_ascii=False)); server.shutdown()

if __name__=="__main__": main()
