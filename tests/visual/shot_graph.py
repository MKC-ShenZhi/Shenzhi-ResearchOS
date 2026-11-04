# -*- coding: utf-8 -*-
"""知识图谱页日/夜截图"""
import subprocess, os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from _tools import edge_path, node_path, out_dir
edge = edge_path()
tmp = out_dir()
base = 'http://localhost:3100'
shots = [
    ('/papers/rdt-1b/graph?theme=light', 'graph-public-day.png'),
    ('/papers/rdt-1b/graph?theme=dark', 'graph-public-night.png'),
    ('/knowledge/graph?theme=light', 'graph-private-day.png'),
    ('/knowledge/graph?theme=dark', 'graph-private-night.png'),
]
for path, out in shots:
    r = subprocess.run([edge, '--headless', '--disable-gpu', '--window-size=1440,1500',
                        '--hide-scrollbars', '--virtual-time-budget=8000',
                        '--screenshot=' + os.path.join(tmp, out), base + path],
                       capture_output=True, text=True)
    lines = (r.stderr or '').strip().splitlines()
    print(out, lines[-1] if lines else 'ok')
    time.sleep(1)
