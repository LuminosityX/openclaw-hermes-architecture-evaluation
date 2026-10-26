#!/usr/bin/env python3
"""Check the configured DeepSeek key using models discovery; never request completion."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from suite import require


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Credential-bearing requests must not redirect to another endpoint')


def check(api_key,open_request=None):
    require(bool(api_key),'DEEPSEEK_API_KEY is not configured in repository Actions secrets')
    request=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+api_key,'Accept':'application/json'})
    opener=open_request or urllib.request.build_opener(NoRedirect()).open
    try:
        with opener(request,timeout=25) as response:
            raw=response.read(1024**2+1)
            require(len(raw)<=1024**2,'Models response exceeds its metadata budget')
            data=json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ValueError(f'DeepSeek models discovery returned HTTP {error.code}; no response body or key is logged') from None
    names=[row.get('id') for row in data.get('data',[])]
    require('deepseek-flash' in names,'The configured DeepSeek account did not advertise deepseek-flash')
    selected=next(row for row in data['data'] if row.get('id')=='deepseek-flash')
    return dict(kind='deepseek-connection-preflight',checked_at_utc=datetime.now(timezone.utc).isoformat(),
                configured=True,authenticated=True,model='deepseek-flash',
                model_metadata={key:selected[key] for key in ['id','name','context_window','max_output_tokens','effort','api_capabilities'] if key in selected},
                completion_requests=0,model_tokens_requested=0,
                campaign_spend_ceiling=None,spending_authorization='Explicit user instruction: no campaign total ceiling',
                limitation='Connectivity/model discovery only; no experiment or paid model completion was executed.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=check(os.environ.get('DEEPSEEK_API_KEY',''))
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(dict(configured=True,authenticated=True,model=result['model'],completion_requests=0)))
    except (ValueError,KeyError,TypeError,OSError) as error:
        parser.exit(1,f'FAIL: {error}\n')


if __name__=='__main__':
    main()
