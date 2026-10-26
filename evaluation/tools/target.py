#!/usr/bin/env python3
"""Resolve the stable OpenClaw campaign pin and verify a published installation."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from suite import MATRIX, load_matrix, require, unique_object


def fetch(url):
    request=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'openclaw-architecture-evaluation'})
    with urllib.request.urlopen(request,timeout=30) as response:
        return json.load(response,object_pairs_hook=unique_object)


def stable_target(release, package, commit):
    require(not release['prerelease'] and not release['draft'], 'Expected a published stable release')
    require(release['tag_name']=='v'+package['version'], 'GitHub stable release and npm latest disagree')
    require(isinstance(commit,str) and len(commit)==40 and all(c in '0123456789abcdef' for c in commit), 'Full release commit required')
    node_minimum=re.search(r'>=([0-9]+\.[0-9]+\.[0-9]+)',package['engines']['node'])
    require(node_minimum is not None,'Resolve a compatible exact Node version explicitly for this engine range')
    return dict(product='openclaw',version=package['version'],source_commit=commit,
                selection_policy='latest-stable-at-campaign-start',release_tag=release['tag_name'],
                release_url=release['html_url'],release_published_at=release['published_at'],
                checked_at_utc=datetime.now(timezone.utc).isoformat(),
                npm_integrity=package['dist']['integrity'],npm_tarball=package['dist']['tarball'],
                node_engine=package['engines']['node'],node_version=node_minimum.group(1),
                pin_policy='Resolve GitHub stable and npm latest together before a campaign; pin version, release commit and package integrity for its duration. Historical bootstrap runs are excluded from current-release conclusions.')


def resolve_latest():
    release=fetch('https://api.github.com/repos/openclaw/openclaw/releases/latest')
    package=fetch('https://registry.npmjs.org/openclaw/latest')
    reference=fetch('https://api.github.com/repos/openclaw/openclaw/git/ref/tags/'+release['tag_name'])['object']
    for _ in range(3):
        if reference['type']=='commit':
            break
        require(reference['type']=='tag','Expected release tag or commit')
        reference=fetch(reference['url'])['object']
    require(reference['type']=='commit','Release tag did not resolve to a commit')
    return stable_target(release,package,reference['sha'])


def require_same_target(pinned, resolved):
    for key in ['product','version','source_commit','npm_integrity','release_tag']:
        require(pinned[key]==resolved[key],f'Campaign target is stale or inconsistent: {key}; refresh explicitly before starting a new campaign')


def verify_installation(target, modules, lock):
    package=json.loads((modules/'openclaw/package.json').read_text(),object_pairs_hook=unique_object)
    build=json.loads((modules/'openclaw/dist/build-info.json').read_text(),object_pairs_hook=unique_object)
    inventory=json.loads(lock.read_text(),object_pairs_hook=unique_object)
    entry=inventory['packages']['node_modules/openclaw']
    require(package['version']==target['version'] and build['version']==target['version'],'Installed OpenClaw version differs from campaign')
    require(build['commit']==target['source_commit'],'Installed build commit differs from the release tag')
    require(entry['version']==target['version'] and entry['integrity']==target['npm_integrity'],'Installed lock entry differs from the pinned registry integrity')
    return dict(kind='published-installation-check',target=target,installed_build=build,
                package_lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(),
                resolved_package_count=len(inventory['packages']),
                version_and_commit_match=True,registry_integrity_matches_lock=True,
                limitation='npm verifies package integrity; this check binds its lock entry and installed build metadata, not an independent source rebuild.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('refresh',help='Explicitly update the campaign pin from official stable metadata')
    commands.add_parser('check-current',help='Fail if the pinned target is no longer current stable')
    verify=commands.add_parser('verify-installation')
    verify.add_argument('--runtime-modules',type=Path,required=True)
    verify.add_argument('--package-lock',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='refresh':
            matrix=json.loads(MATRIX.read_text(),object_pairs_hook=unique_object)
            matrix['target']=resolve_latest()
            MATRIX.write_text(json.dumps(matrix,ensure_ascii=False,indent=2)+'\n')
            result=matrix['target']
        elif args.command=='check-current':
            target=load_matrix()['target']
            resolved=resolve_latest()
            require_same_target(target,resolved)
            result=dict(current_stable=True,target=target)
        else:
            result=verify_installation(load_matrix()['target'],args.runtime_modules,args.package_lock)
        print(json.dumps(result,indent=2))
    except (ValueError,KeyError,TypeError,OSError) as error:
        parser.exit(1,f'FAIL: {error}\n')


if __name__=='__main__':
    main()
