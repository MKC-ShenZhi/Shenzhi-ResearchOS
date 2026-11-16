# -*- coding: utf-8 -*-
"""截图脚本共用的本机工具定位:环境变量优先,否则按平台取默认路径。"""
import os, shutil, sys, tempfile


def edge_path():
    if os.environ.get('EDGE_PATH'):
        return os.environ['EDGE_PATH']
    if sys.platform == 'win32':
        return r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    if sys.platform == 'darwin':
        return '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    return shutil.which('microsoft-edge') or 'microsoft-edge'


def node_path():
    return os.environ.get('NODE_BIN') or shutil.which('node') or 'node'


def out_dir():
    """截图输出目录:SHOT_OUT_DIR,默认系统临时目录。"""
    return os.environ.get('SHOT_OUT_DIR') or tempfile.gettempdir()
