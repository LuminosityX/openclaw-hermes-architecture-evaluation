"""Establish official provenance using the public native pinned npm installer."""
from runtime import R,save
from run_state_ops import cli
from run_install_rebuild import operator_install

def install(run):
 user=R/'runtime/npm-empty-user-config';glob=R/'runtime/npm-empty-global-config';user.write_text('');glob.write_text('');cache=R/'runtime/npm-cache';cache.mkdir(exist_ok=True)
 command=['env','NPM_CONFIG_USERCONFIG=/native-config/user','NPM_CONFIG_GLOBALCONFIG=/native-config/global','NPM_CONFIG_CACHE=/native-npm-cache',*cli('openclaw',['plugins','install','@openclaw/diagnostics-otel@2026.10.6','--force','--accept-capabilities'])]
 rec=operator_install(run,'openclaw',command,[(user,'/native-config/user',True),(glob,'/native-config/global',True),(cache,'/native-npm-cache',False)],'/workspace')
 save(run/'native-addon-install.json',{**rec,'source':'Public native plugin install with pinned official npm spec; no local copy promoted to trusted origin.'});return rec
