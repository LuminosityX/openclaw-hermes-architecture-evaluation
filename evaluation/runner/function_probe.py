"""Run generated solution functions; output values, never grade them here.

Mounted alone in a disposable acceptance namespace. Expected answers and
provider credentials are absent. The host compares these returned values.
"""
import json
import runpy
import sys

query=json.loads(sys.stdin.read(128*1024))
namespace=runpy.run_path('/artifact/solution.py')
function=namespace[query['function']]
results=[]
for arguments in query['inputs']:
    try: results.append(function(arguments))
    except BaseException as error: results.append(dict(error=type(error).__name__))
sys.stdout.write('\nEVAL_FUNCTION_RESULTS:'+json.dumps(results,ensure_ascii=False,separators=(',',':'))+'\n')
