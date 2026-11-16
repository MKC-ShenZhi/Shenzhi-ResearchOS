# -*- coding: utf-8 -*-
import subprocess, os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from _tools import edge_path, node_path, out_dir
edge = edge_path()
node = node_path()
cdp_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot-cdp.mjs')
tmp = out_dir()
base = 'http://localhost:3100'
# 元组:(路径, 输出, 宽, 高[, virtual-time 预算[, 等待文本]])
# 带「等待文本」的页面走 shot-cdp.mjs(CDP 真实时间等待,适合 effect 驱动的视图);
# 其余走 Edge --screenshot + virtual-time-budget(适合 SSR 直出页)。
pages = [
    ('/', 'f_home.png', 1440, 1500),
    ('/submit', 'f_submit.png', 1440, 1650),
    ('/papers/rdt-1b', 'f_paper.png', 1440, 1100),
    ('/scholars', 'f_scholars.png', 1440, 1250),
    ('/scholars/kaiming-he', 'f_scholar_detail.png', 1440, 1500),
    ('/knowledge', 'f_knowledge.png', 1440, 900),
    ('/agents', 'f_agents.png', 1440, 1500),
    ('/agents/deep-search?q=diffusion', 'f_deep_search.png', 1440, 1650),
    ('/agents/deep-research', 'f_dr_home.png', 1440, 1250),
    ('/agents/deep-research?autostart=1', 'f_dr_running.png', 1440, 1500, None, '撰写第 2 节'),
    ('/agents/deep-research?mode=instant', 'f_dr_report.png', 1440, 2400, None, '参考文献'),
]
for p in pages:
    path, out, w, h = p[:4]
    budget = p[4] if len(p) > 4 else 6000
    wait_text = p[5] if len(p) > 5 else None
    if wait_text:
        cmd = [node, cdp_script, '--url', base + path,
               '--out', os.path.join(tmp, out),
               '--width', str(w), '--height', str(h), '--wait-text', wait_text]
    else:
        cmd = [edge, '--headless', '--disable-gpu', f'--window-size={w},{h}',
               '--hide-scrollbars', f'--virtual-time-budget={budget or 6000}',
               '--screenshot=' + os.path.join(tmp, out), base + path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = ((r.stdout or '') + (r.stderr or '')).strip().splitlines()
    print(out, lines[-1] if lines else 'ok')
    time.sleep(1)
