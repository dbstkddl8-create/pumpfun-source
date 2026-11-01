#!/usr/bin/env python3
"""rec.py <name> <status> <hypothesis> <json data>: one ledger row for this lane (approach stitch16, key
0x22a10-w16-5998913-stitch16-<name>-v1)."""
import sys,subprocess,json
L='/Users/shawwalters/Documents/Codex/2026-10-24/pump-main-swarm/worktrees/w16a17-cto-stitch16/reconstruction/pump-main/log_attempt.py'
n,st,h,d=sys.argv[1:5]
k=f'0x22a10-w16-5998913-stitch16-{n}-v1'
c=subprocess.run(['python3',L,'check','--dedupe-key',k],capture_output=True,text=True)
print('check:',c.stdout.strip()[:200],c.returncode)
r=subprocess.run(['python3',L,'record','--lane','w16a17-cto-stitch16','--approach','stitch16','--target','0x22a10','--dedupe-key',k,'--hypothesis',h,'--status',st,'--data',d],capture_output=True,text=True)
print('record:',r.returncode,r.stdout.strip()[:200],r.stderr.strip()[:300])
