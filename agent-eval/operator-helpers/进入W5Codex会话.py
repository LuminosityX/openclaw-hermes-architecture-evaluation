#!/usr/bin/env python3
"""Run this on the experiment Linux host from your Windows SSH terminal."""
import json
import os
from pathlib import Path
import subprocess
import sys

RUN=Path('/root/Downloads/1023magnitude/agent_eval_handoff/runs/pilot/codex/W5/v1/r1')
WORKSPACE=RUN/'workspace'
SOCKET=RUN/'runtime-state/observer.sock'
THREAD_ID='01a16c37-5b91-7bd1-ac2c-ac151a279494'
if not sys.stdin.isatty():
    raise SystemExit('请在连接实验主机的交互式SSH终端中运行。')
if not SOCKET.exists():
    raise SystemExit('W5实验入口当前离线，请回到协调聊天通知助手；不要另建任务。')
args=['bwrap','--unshare-all','--die-with-parent','--new-session','--cap-drop','ALL',
      '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
      '--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/root',
      '--ro-bind',str(WORKSPACE),'/workspace','--chdir','/workspace',
      '--ro-bind',str(SOCKET),'/backend/control.sock',
      '--setenv','PATH','/usr/local/bin:/usr/bin:/bin']
for path in ['/etc/alternatives','/etc/passwd','/etc/group','/etc/ssl/certs']:
    if Path(path).exists():args+=['--ro-bind',path,path]
args+=['--','codex','--remote','unix:///backend/control.sock','resume','--model','gpt-6.1-sol','-c','model_reasoning_effort="medium"',THREAD_ID]
print('正在连接独立实验机 agent-eval-w5-codex 的现有任务：W5 Codex 跨端审批 · 1024。')
print('进入后核对现有计划与校验号即可；无需重复发送初始指令，也暂不执行受控写入。')
raise SystemExit(subprocess.call(args))
