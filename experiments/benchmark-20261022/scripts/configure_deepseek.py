"""One-time private terminal prompt. Never echoes or logs the API key."""
import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path('/root/.config/openclaw-hermes-benchmark')
KEY_FILE = PRIVATE / 'deepseek.key'
BASE_URL = 'https://api.deepseek.com'
MODEL = 'deepseek-flash'

def configured_key():
    value = os.environ.get('DEEPSEEK_API_KEY')
    if value:
        return value.strip()
    if KEY_FILE.exists():
        if KEY_FILE.is_symlink() or KEY_FILE.stat().st_mode & 0o077:
            raise RuntimeError('Private key file must be a regular file with mode0600')
        return KEY_FILE.read_text().strip()
    return None

def main():
    parser = argparse.ArgumentParser(description='Securely enter your DeepSeek key; no environment setup required.')
    parser.add_argument('--status', action='store_true', help='Report only whether a key has been configured; no network request.')
    args = parser.parse_args()
    if args.status:
        print(json.dumps({'base_url':BASE_URL,'model':MODEL,'key_configured':bool(configured_key())}))
        return 0
    if not sys.stdin.isatty():
        print('Run this command in an interactive terminal. The API key will be hidden while you paste it.',file=sys.stderr)
        return 2
    key = getpass.getpass('粘贴 DeepSeek API key 后按回车（输入不会显示）：').strip()
    if not key or any(c.isspace() for c in key):
        print('密钥为空或包含空白；未保存。',file=sys.stderr)
        return 2
    request = urllib.request.Request(BASE_URL+'/models',headers={'Authorization':'Bearer '+key,'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            data=json.load(response)
            if not isinstance(data.get('data'),list):
                raise RuntimeError('Unexpected models response')
    except urllib.error.HTTPError as error:
        print(f'连接验证未通过（HTTP {error.code}）；密钥未保存。',file=sys.stderr)
        return 1
    except Exception as error:
        print(f'连接验证未完成（{type(error).__name__}）；密钥未保存。',file=sys.stderr)
        return 1
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    PRIVATE.chmod(0o700)
    fd,temporary=tempfile.mkstemp(prefix='.deepseek-',dir=PRIVATE)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as output:output.write(key+'\n')
        os.replace(temporary,KEY_FILE)
    finally:
        if Path(temporary).exists():Path(temporary).unlink()
    (ROOT/'results/deepseek-status.json').write_text(json.dumps({'base_url':BASE_URL,'model':MODEL,'key_configured':True,'validation':'Authenticated models listing; no generated tokens','secret_location':'Private file outside experiment artifacts; not included in reports'},indent=2))
    print('已安全保存并验证连接。两套实验将使用 deepseek-flash；密钥不会写入实验目录或报告。')
    return 0

if __name__=='__main__':raise SystemExit(main())
