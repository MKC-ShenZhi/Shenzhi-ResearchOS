# -*- coding: utf-8 -*-
"""日/夜模式对比截图:?theme=dark 由 layout 内联脚本识别"""
import subprocess, os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from _tools import edge_path, node_path, out_dir
edge = edge_path()
node = node_path()
cdp_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot-cdp.mjs')
tmp = out_dir()
base = 'http://localhost:3100'
# 元组:(路径, 输出[, 等待文本]);带等待文本的走 CDP(shot-cdp.mjs),其余 Edge --screenshot
shots = [
    ('/?theme=light', 'theme-home-day.png'),
    ('/?theme=dark', 'theme-home-night.png'),
    ('/agents?theme=dark', 'theme-agents-night.png'),
    ('/scholars?theme=dark', 'theme-scholars-night.png'),
    ('/submit?theme=dark', 'theme-submit-night.png'),
    ('/agents/deep-research?theme=dark', 'theme-dr-home-night.png'),
    ('/agents/deep-research?mode=instant&theme=dark', 'theme-dr-report-night.png', '参考文献'),
]
for s in shots:
    path, out = s[:2]
    wait_text = s[2] if len(s) > 2 else None
    if wait_text:
        cmd = [node, cdp_script, '--url', base + path,
               '--out', os.path.join(tmp, out),
               '--width', '1440', '--height', '2400', '--wait-text', wait_text]
    else:
        cmd = [edge, '--headless', '--disable-gpu', '--window-size=1440,1500',
               '--hide-scrollbars', '--virtual-time-budget=8000',
               '--screenshot=' + os.path.join(tmp, out), base + path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = ((r.stdout or '') + (r.stderr or '')).strip().splitlines()
    print(out, lines[-1] if lines else 'ok')
    time.sleep(1)
