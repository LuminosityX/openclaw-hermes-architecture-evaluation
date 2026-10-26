"""Cheap checks for the pilot's host-storage and namespace contract."""

import importlib.util
from pathlib import Path
import sys
import unittest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location('local_runner',TOOLS/'run_local.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class LocalRunnerTests(unittest.TestCase):
    def command(self):
        return runner.sandbox_command(Path('/existing/modules'),Path('/existing/node'),64,['--study','ARC-01','--blocks','2'])

    def test_scratch_has_kernel_size_limit_and_no_writable_host_bind(self):
        command=self.command()
        index=command.index('--tmpfs')
        self.assertEqual(command[index-2:index+2],['--size',str(64*1024**2),'--tmpfs','/scratch'])
        self.assertNotIn('--bind',command)
        self.assertEqual(command.count('--tmpfs'),1)

    def test_runtime_and_driver_are_read_only(self):
        command=self.command()
        readonly=[command[i+1:i+3] for i,arg in enumerate(command) if arg=='--ro-bind']
        self.assertIn(['/existing/modules','/runtime/node_modules'],readonly)
        self.assertIn(['/existing/node','/toolchain/node'],readonly)
        self.assertTrue(any(pair[1]=='/driver' for pair in readonly))

    def test_network_and_process_namespaces_are_separate(self):
        command=self.command()
        self.assertIn('--unshare-all',command)
        self.assertNotIn('--share-net',command)
        self.assertIn('--die-with-parent',command)
        self.assertIn('--cap-drop',command)

    def test_state_temp_and_cache_stay_in_scratch(self):
        command=self.command()
        self.assertIn('scratch/tmp',command)
        self.assertIn('scratch/home',command)
        self.assertIn('/scratch/cache',command)
        self.assertIn('NODE_DISABLE_COMPILE_CACHE',command)

    def test_owned_ssh_retains_only_required_daemon_capabilities(self):
        command=runner.sandbox_command(Path('/existing/modules'),Path('/existing/node'),64,[],ssh_backend=True)
        self.assertIn('--unshare-net',command)
        self.assertIn('--unshare-pid',command)
        self.assertNotIn('--share-net',command)
        capabilities=[command[i+1] for i,arg in enumerate(command) if arg=='--cap-add']
        self.assertEqual(set(capabilities),{'CAP_SETUID','CAP_SETGID','CAP_SYS_CHROOT'})
        self.assertNotIn('CAP_SYS_ADMIN',capabilities)

    def test_phase_measurement_mount_is_read_only_and_run_owned(self):
        command=runner.sandbox_command(Path('/existing/modules'),Path('/existing/node'),64,[],measurement_group=Path('/owned/cgroup'))
        readonly=[command[i+1:i+3] for i,arg in enumerate(command) if arg=='--ro-bind']
        self.assertIn(['/owned/cgroup','/measurement/cgroup'],readonly)
        self.assertNotIn('--bind',command)

    def test_old_runtime_cannot_become_current_release_evidence(self):
        target=dict(version='2026.10.7',source_commit='a'*40)
        old=dict(version='2026.9.2',commit='b'*40)
        with self.assertRaisesRegex(ValueError,'pinned current stable'):
            runner.runtime_role(old,target)
        self.assertEqual(runner.runtime_role(old,target,allow_historical=True),'historical-bootstrap-only')
        self.assertEqual(runner.runtime_role(dict(version=target['version'],commit=target['source_commit']),target),'current-stable-pilot')

    def test_timeout_recovers_completed_arms_without_claiming_the_whole_study(self):
        import json
        frame=dict(kind='arm-checkpoint',product='openclaw',study='SRC-01',planned_arms=8,arm=dict(block=0,valid=True))
        result=runner.decode_report(json.dumps(frame)+'\n{"truncated":')
        self.assertEqual(len(result['studies'][0]['arms']),1)
        self.assertFalse(result['studies'][0]['complete'])
        self.assertTrue(result['harness_error'])

    def test_final_error_does_not_discard_an_earlier_arm_checkpoint(self):
        import json
        frame=dict(kind='arm-checkpoint',product='openclaw',study='SRC-02',planned_arms=8,arm=dict(block=0,valid=True))
        final=dict(kind='exploratory-pilot',product='openclaw',studies=[],harness_error='later fixture failure')
        result=runner.decode_report(json.dumps(frame)+'\n'+json.dumps(final))
        self.assertEqual(len(result['studies'][0]['arms']),1)
        self.assertTrue(result['checkpoint_recovery_used'])

    def test_adapter_timeout_preserves_observation_without_awarding_full_coverage(self):
        import json
        observation=dict(scenario_id='REL-14-S01',unit=1,state='pass')
        result=runner.decode_report(json.dumps(dict(kind='adapter-validation-checkpoint',product='openclaw',observation=observation)))
        self.assertEqual(result['observations'],[observation])
        self.assertTrue(result['harness_error'])


if __name__=='__main__':
    unittest.main()
