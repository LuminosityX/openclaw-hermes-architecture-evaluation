"""Use the public native npm installer to establish verified official provenance.
No internal-capability marker is forged and no live Gateway is modified.
"""
import os
from runtime import R,save
from run_state_ops import cli
from run_install_rebuild import operator_install

def install(run):
 user=R/'runtime/npm-empty-user-config';glob=R/'runtime/npm-empty-global-config';user.write_text('');glob.write_text('');cache=R/'runtime/npm-cache';cache.mkdir(exist_ok=True)
 # CLI's npm subprocess gets only evaluator-owned empty config and cache;
 # installation has network, while actual agent/exporter run remains offline.
 command=cli('openclaw',['plugins','install','@openclaw/diagnostics-otel@2026.10.6','--force','--accept-capabilities'])
 original=os.environ.copy()
 try:
  os.environ.update(NPM_CONFIG_USERCONFIG='/native-config/user',NPM_CONFIG_GLOBALCONFIG='/native-config/global',NPM_CONFIG_CACHE='/native-npm-cache')
  # operator_install forwards a strict allowlist; place npm settings directly
  # on the native command instead of depending on controller environment.
  command=['env','NPM_CONFIG_USERCONFIG=/native-config/user','NPM_CONFIG_GLOBALCONFIG=/native-config/global','NPM_CONFIG_CACHE=/native-npm-cache',*command]
  rec=operator_install(run,'openclaw',command,[(user,'/native-config/user',True),(glob,'/native-config/global',True),(cache,'/native-npm-cache',False)],'/workspace')
 finally:os.environ.clear();os.environ.update(original)
 save(run/'native-addon-install.json',{**rec,'source':'Public native plugin install with pinned official npm spec; linked/local copies are not promoted to trusted official origin.'});return rec
