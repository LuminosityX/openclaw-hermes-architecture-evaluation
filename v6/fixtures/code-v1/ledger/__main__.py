import sys,json
from .core import reconcile
from .io import read_events
print(json.dumps(reconcile(read_events(sys.argv[1]))))
