"""A01 explanatory isolated fork: remove only call_tool's per-connection lock.
Not product baseline, not a recommendation: discovery/health locks and shared callback context retain their original assumptions.
"""
import hashlib,json,os,shutil,types
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from run_native_suite import M

def prepare():
 target=R/'runtime/hermes-mcp-lock-ablation'
 if (target/'ABLATION-MANIFEST.json').exists():return target
 if target.exists():raise RuntimeError('Partial ablation fork retained')
 shutil.copytree(R/'runtime/hermes-stable',target,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
 p=target/'tools/mcp_tool_handlers.py';source=p.read_text();needle='async with server._rpc_lock, _track_inflight_rpc(server, server_name, op, retry_safe=read_only):'
 if source.count(needle)!=1:raise RuntimeError('Precisely one intended call-tool lock seam required')
 p.write_text(source.replace(needle,'async with _track_inflight_rpc(server, server_name, op, retry_safe=read_only):'));save(target/'ABLATION-MANIFEST.json',dict(change='Remove only server._rpc_lock from call_tool context manager, keep inflight tracking and every other RPC lock unchanged.',file='tools/mcp_tool_handlers.py',before_sha256=hashlib.sha256(source.encode()).hexdigest(),after_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),baseline_credit=False,limits='Read-only delay workload. Discovery/health/callback contention and untrusted heterogeneous sessions require separate stress tests; no claim of production correctness or safe removal.'))
 return target

def main():
 os.chdir(OLD);fork=prepare();results=[]
 def box(state,work,relay_dir=None,family=None,command=None,evaluator=None):return sandbox(state,work,family,command,relay_dir,[(fork,'/runtime/hermes-source',True)])
 M.C=types.SimpleNamespace(configuration=configuration,sandbox=box,product_command=command)
 for unit in range(1,7):
  root=R/'native-ablation'/f'u{unit}';(root/'evidence').mkdir(parents=True,exist_ok=True);M.R=root;p=root/'runs-mechanisms/mcp/hermes/result.json';result=json.loads(p.read_text()) if p.exists() else M.run_one('hermes','mcp');baseline=R/'native-units'/f'u{unit}'/'runs-mechanisms/mcp/hermes/result.json'
  if not baseline.exists():raise RuntimeError('Native stable baseline must run first')
  rec=dict(independent_unit=unit,stable_baseline=json.loads(baseline.read_text()),isolated_lock_ablation=result,baseline_credit=False,interpretation='Changes in tool interval/overlap identify the serialization cost for this workload. Do not generalize to callback/discovery safety or credit modified behavior to Hermes.');results.append(rec);save(R/'results/mcp-lock-ablation.json',results)
 print('MCP_LOCK_ABLATION_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
