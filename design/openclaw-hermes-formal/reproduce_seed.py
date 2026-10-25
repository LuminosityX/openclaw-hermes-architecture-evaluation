"""Reproduce the historical real-project task seed. No model or network call."""
from pathlib import Path
import json,sys
R=Path(__file__).resolve().parent
sys.path.insert(0,str(next((R/'vendor').glob('pluggy-1.5.0-*.whl'))))
import pluggy
spec=pluggy.HookspecMarker('atomic');impl=pluggy.HookimplMarker('atomic')
class Spec:
    @spec
    def hello(self,value):pass
class Bad:
    @impl
    def hello(self,value,unexpected):return value
pm=pluggy.PluginManager('atomic');pm.add_hookspecs(Spec);candidate=Bad();failed=False
try:pm.register(candidate,name='bad')
except pluggy.PluginValidationError:failed=True
result=dict(project='pluggy',version=pluggy.__version__,validation_error_raised=failed,failed_plugin_still_registered=pm.get_plugin('bad') is candidate,model_calls=0)
assert result['validation_error_raised'] and result['failed_plugin_still_registered']
print(json.dumps(result,ensure_ascii=False,indent=2))
