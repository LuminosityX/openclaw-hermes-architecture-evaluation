import os,sys
from pathlib import Path
if sys.executable != '/usr/bin/python3':
 os.environ.pop('PYTHONPATH',None);os.execv('/usr/bin/python3',['/usr/bin/python3',*sys.argv])
stdlib=[p for p in sys.path if ('python3.12' in p or p.endswith('python312.zip')) and 'site-packages' not in p and 'dist-packages' not in p]
sys.path[:]=[str(Path(__file__).parent/'project/src'),*(str(x) for x in Path('/test-wheels').glob('*.whl')),*stdlib]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
import pytest
raise SystemExit(pytest.main(['project/testing','-q','--disable-warnings']))
