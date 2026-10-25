#!/usr/bin/env python3
"""Enter an experiment API key locally without echo, history, logs or network.

The credential is kept outside outputs, the handoff package and public tasks.
This helper never calls DeepSeek or starts an evaluated Agent.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

EXPERIMENT_ROOT = Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval')
SECRET_DIR = EXPERIMENT_ROOT / 'work/runtime-secrets'
SECRET_PATH = SECRET_DIR / 'deepseek.json'


def require_private_directory(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or directory.is_symlink():
        raise RuntimeError('密钥目录不是普通目录，已停止。')
    if info.st_uid != os.getuid():
        raise RuntimeError('密钥目录不属于当前用户，已停止。')
    directory.chmod(0o700)


def save_secret(key, destination):
    require_private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise RuntimeError('已有密钥文件；为保留原配置，本工具不会覆盖。')
    descriptor, temporary_name = tempfile.mkstemp(prefix='.deepseek-entry-', dir=destination.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'DEEPSEEK_API_KEY': key, 'DEEPSEEK_BASE_URL': 'https://api.deepseek.com'}, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # An atomic no-overwrite hard link also refuses a symlink destination.
        os.link(temporary_path, destination, follow_symlinks=False)
    finally:
        temporary_path.unlink(missing_ok=True)


def check_presence():
    try:
        info = SECRET_PATH.lstat()
    except FileNotFoundError:
        print('尚未配置实验密钥。')
        return 1
    safe = (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600
            and stat.S_IMODE(SECRET_DIR.lstat().st_mode) == 0o700
            and not SECRET_DIR.is_symlink() and info.st_size > 0)
    print('实验密钥文件已存在，权限正确；未读取内容，尚未验证 API 有效性。'
          if safe else '密钥文件或目录权限不符合要求，已停止。')
    return 0 if safe else 2


def main():
    parser = argparse.ArgumentParser(description='本地隐藏输入 DeepSeek 实验密钥，不发起网络请求。')
    parser.add_argument('--check', action='store_true', help='只检查文件存在性和权限，不读取密钥。')
    args = parser.parse_args()
    if args.check:
        return check_presence()
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print('请在交互终端运行；本工具拒绝回显输入、管道、聊天或命令行参数传入密钥。', file=sys.stderr)
        return 2
    if SECRET_PATH.exists() or SECRET_PATH.is_symlink():
        print('已有实验密钥文件，未读取或覆盖；使用 --check 检查权限。', file=sys.stderr)
        return 2
    print('仅在本地终端粘贴 API key；输入不会显示。不会验证或调用 API。')
    key = getpass.getpass('DeepSeek API key（隐藏输入）: ').strip()
    if not key or any(character.isspace() for character in key):
        print('输入为空或包含空白，未保存。', file=sys.stderr)
        return 2
    try:
        save_secret(key, SECRET_PATH)
    except (OSError, RuntimeError):
        print('未能安全保存密钥；没有启动 API 调用。', file=sys.stderr)
        return 2
    finally:
        key = None
    print('已保存到实验专用受限目录；不会加入评估记录、公开工作区或输出快照。')
    print('请回到聊天只回复“密钥已配置”。预算和 adapter 门禁通过前不会调用模型。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
