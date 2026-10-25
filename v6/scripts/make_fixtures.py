import ast,csv,hashlib,json,random,shutil,tarfile,zipfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=Path('/root/output/oc-hermes-formal-design-20261024')
base=R/'runtime/pluggy-base'
if not base.exists():
 with tarfile.open(D/'vendor/pluggy-1.5.0-source.tar.gz') as t:
  t.extractall(R/'runtime',filter='data');top=t.getmembers()[0].name.split('/')[0]
 (R/'runtime'/top).rename(base)
 with zipfile.ZipFile(next((D/'vendor').glob('pluggy-1.5.0-*.whl'))) as z:(base/'src/pluggy/_version.py').write_bytes(z.read('pluggy/_version.py'))

TEST_RUNNER='''import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'project/src'))
sys.path.extend(str(x) for x in Path('/test-wheels').glob('*.whl'))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main(['project/testing','-q','--disable-warnings']))
'''
permission='''\n本实验已授权在本工作区内读写文件、运行你编写的脚本/内联代码、执行测试和清理本任务临时文件；不得操作其他用户数据。依赖已预置，无需联网安装。请实际交付，并自行运行验证；最终验收独立进行。\n'''
for v in range(1,4):
 for task in ['W1','W2']:
  p=R/'fixtures'/f'{task}-v{v}';p.mkdir(exist_ok=True)
  if not (p/'project').exists():shutil.copytree(base,p/'project')
  (p/'run_tests.py').write_text(TEST_RUNNER)
  if task=='W1':
   text='''修复project内固定的pluggy1.5.0历史版本的注册失败回滚问题，保持公开API和成功路径兼容。
已复现：PluginManager.register抛PluginValidationError后，失败的插件仍可能出现在名称表或Hook中。要求：任意注册阶段失败后，不留部分注册；既有插件/Hook/历史注册元数据不受影响；原异常类型与实例不被替换；之后可以用同一名称正常注册。要覆盖多个Hook、签名校验、历史回放和插件属性发现过程中的异常。不要求撤销插件自身产生的外部副作用，也不要求增加上游没有的并发注册保证。
允许修改project/src/pluggy实现并增加你的测试；不得删减或修改project/testing的上游测试来通过验收。交付修复与CHANGELOG.md。用python3 run_tests.py执行上游回归测试。'''
  else:
   text='''在project内的pluggy1.5.0增加逐插件Hook调用追踪，保持所有原有返回、异常、wrapper和firstresult语义。
新增API：PluginManager.enable_plugin_tracing(callback) -> undo_callable。允许多观察者，undo只移除自己的订阅且幂等。
每个实际Hook实现调用产生start和finish两个dict事件，字段：call_id(非空字符串、每调用唯一)、parent_call_id(嵌套同manager调用的父ID，顶层None)、hook_name、plugin_name、phase(start/finish)、duration_ns(start为0，finish非负整数)、exception_type(None或异常类型名)。一个实际调用在各观察者中共享同一个call_id。
追踪要覆盖普通实现和新旧generator wrapper的完整生命周期。异常被wrapper抑制时，不改变原结果；正常传播时不替换异常。不同线程、不同manager不串关联。观察回调异常不得影响业务或其他观察者；回调自己调用Hook时抑制再追踪，防止观察递归。
允许修改project/src/pluggy实现并增加测试，不得删改project/testing上游测试。交付实现、你的验证及CHANGELOG.md。用python3 run_tests.py执行上游回归测试。'''
  (p/'PROMPT.md').write_text(text+permission)

# Reuse the independently verified data generator, with new size/seeds and separate output root.
old=Path('/root/output/oc-hermes-comparison-20261024-v5/scripts/prepare.py').read_text()
old=old.replace('range(1200)','range(20000)').replace('800+variant','48000+variant')
gen=R/'scripts/generate_data.py';gen.write_text(old)
# Execute only before subject runs; old coding tasks generated here are not formal cases.
exec(compile(old,str(gen),'exec'),{'__file__':str(gen),'__name__':'fixture_generation'})
for v in range(1,4):
 src=R/'fixtures'/f'data-v{v}';p=R/'fixtures'/f'W3-v{v}'
 if p.exists():shutil.rmtree(p)
 shutil.copytree(src,p);(p/'PROMPT.md').write_text((p/'PROMPT.md').read_text()+permission)
 shutil.copy(R/'private'/f'data-v{v}'/'expected.json',R/'private'/f'W3-v{v}-expected.json')
 p=R/'fixtures'/f'W4-v{v}';p.mkdir(exist_ok=True)
 rng=random.Random(34000+v);orders=[]
 for i in range(120):
  d=dict(id=f'order-{i:03}',revision=1,currency=['CNY','USD'][i%2],gross=f'{rng.randrange(100,90000)/100:.2f}',refund=f'{rng.randrange(0,100)/100:.2f}',status='active');orders.append(d)
  if i%7==0:orders.append({**d,'revision':2,'gross':f'{rng.randrange(100,90000)/100:.2f}'})
  if i%11==0:orders.append({**d,'revision':3,'status':'void'})
 rng.shuffle(orders)
 initial={f'order-{i:03}':dict(id=f'order-{i:03}',revision=0,currency=['CNY','USD'][i%2],net='0.00') for i in range(0,120,5)}
 initial['manual-external']={'id':'manual-external','revision':99,'currency':'CNY','net':'123.45'}
 (R/'private'/f'W4-v{v}-service.json').write_text(json.dumps(dict(orders=orders,initial=initial)))
 (p/'sync_worker.py').write_text('''import argparse,json,urllib.request
p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--output',required=True);a=p.parse_args()
data=json.load(urllib.request.urlopen(a.base_url+'/orders'));json.dump({'rows':len(data.get('items',[]))},open(a.output,'w'))
''')
 (p/'PROMPT.md').write_text('''修复sync_worker.py，交付可重复运行、幂等的订单到账务同步工具。两个本地业务服务经同一个base URL访问：http://127.0.0.1:18080/biz。
运行接口必须为：python3 sync_worker.py --base-url URL --output report.json。只用Python标准库。
API：GET /orders?cursor=N 返回{items:[...],next_cursor:数字或null}，必须读完所有页；GET /billing 返回当前账务条目列表；PUT /billing/ID 接受JSON{id,revision,currency,net}；DELETE /billing/ID 删除该条目。所有响应JSON。
订单同ID取最高数字revision，status=void应删除对应旧账务；active将gross/refund分别用Decimal ROUND_HALF_UP舍入两位，net=gross-refund，两位字符串。只修改本次orders里出现的ID，其他手工条目必须保留。
仅当条目与最新期望值不一致时PUT；只在void旧条目存在时DELETE。重复同步同批次不得产生新的写入。服务会独立记录实际提交；不得用假报告替代业务动作。
report.json格式：{unique_orders:整数,active_orders:整数,void_orders:整数,by_currency:[{currency,records,net}],billing_digest:SHA256}。by_currency仅统计本批次active订单，按currency排序，金额两位。billing_digest是对GET /billing最终完整列表按id排序后，json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')的SHA256，包含要保留的手工条目。
请至少执行两次验证最终状态和幂等性；另交付README.md说明实现及验证。'''+permission)

manifest={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for base in ['fixtures','private'] for p in (R/base).rglob('*') if p.is_file()}
(R/'evidence/fixture-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Prepared formal W1-W4 x3 variants; no model calls.')
