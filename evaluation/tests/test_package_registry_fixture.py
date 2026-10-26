"""The owned registry faults are actual transport and integrity interventions."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from package_registry_fixture import PackageRegistry,DEPENDENCY,VERSION

class PackageRegistryTest(unittest.TestCase):
    def setUp(self):self.peer=PackageRegistry()
    def tearDown(self):self.peer.close()
    def get(self,path):
        c=http.client.HTTPConnection('127.0.0.1',18091,timeout=3);c.request('GET',path);r=c.getresponse()
        try:return r.status,r.read()
        finally:c.close()
    def test_metadata_integrity_agrees_only_in_the_healthy_arm(self):
        for mode,expected in [('healthy',True),('checksum',False)]:
            self.peer.mode=mode;status,raw=self.get('/'+DEPENDENCY);self.assertEqual(status,200)
            dist=json.loads(raw)['versions'][VERSION]['dist'];actual='sha512-'+base64.b64encode(hashlib.sha512(self.peer.raw).digest()).decode()
            self.assertEqual(actual==dist['integrity'],expected)
        self.peer.mode='missing';self.assertEqual(self.get('/'+DEPENDENCY)[0],404)
    def test_substitution_really_changes_served_bytes_under_original_integrity(self):
        self.peer.mode='substitution';_,metadata=self.get('/'+DEPENDENCY)
        dist=json.loads(metadata)['versions'][VERSION]['dist']
        status,raw=self.get('/'+DEPENDENCY+'/-/'+DEPENDENCY+'-'+VERSION+'.tgz')
        self.assertEqual(status,200)
        self.assertNotEqual(raw,self.peer.raw)
        actual='sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()
        original='sha512-'+base64.b64encode(hashlib.sha512(self.peer.raw).digest()).decode()
        self.assertEqual(dist['integrity'],original)
        self.assertNotEqual(actual,dist['integrity'])

    def test_partial_body_really_violates_its_http_length(self):
        self.peer.mode='partial'
        with self.assertRaises(http.client.IncompleteRead):self.get('/'+DEPENDENCY+'/-/'+DEPENDENCY+'-'+VERSION+'.tgz')
