"""The reference must expose real Stop forwarding before observing cancellation."""
from pathlib import Path
import subprocess
import unittest


class HarnessActiveHandleTest(unittest.TestCase):
    def test_registered_active_handle_forwards_abort_once_and_rejects_steering(self):
        module=(Path(__file__).resolve().parents[1]/'runner/harness_reference.mjs').as_uri()
        source="""import assert from 'node:assert/strict';
import {createOwnedActiveRun} from MODULE;
let killed=0,noticed=0,running=true;
const handle=createOwnedActiveRun({runId:'owned-run',toolAuthorityFingerprint:'exact-host-attempt',onAttemptAbort(){noticed++;}},()=>{killed++;},()=>running);
assert.equal(handle.toolAuthorityFingerprint,'exact-host-attempt');
assert.equal(handle.isStreaming(),true);assert.equal(handle.isAborted(),false);
handle.abort();handle.abort();assert.equal(killed,1);assert.equal(noticed,1);
assert.equal(handle.isStreaming(),false);assert.equal(handle.isAborted(),true);
await assert.rejects(handle.queueMessage('unsafe steering'),/DOES_NOT_ACCEPT_STEERING/);
running=false;assert.equal(handle.isStopped(),true);
""".replace('MODULE',repr(module))
        result=subprocess.run(['node','--input-type=module','-e',source],capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
