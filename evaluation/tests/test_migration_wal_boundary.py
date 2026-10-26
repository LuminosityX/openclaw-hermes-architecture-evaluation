"""A changed page is eligible only when its real schema identity matches."""
import struct
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from migration_trace import schema_payload

class MigrationBoundaryTest(unittest.TestCase):
    def test_real_sqlite_page_layout_and_coalesced_frame(self):
        page=bytearray(4096);page[:16]=b'SQLite format 3\0'
        struct.pack_into('>I',page,40,109);struct.pack_into('>I',page,60,25)
        self.assertEqual(schema_payload(page,25,108)['schema_cookie'],109)
        self.assertIsNone(schema_payload(page,25,109))
        self.assertIsNone(schema_payload(page,24,108))
        frame=struct.pack('>6I',1,0,0,0,0,0)+page
        self.assertEqual(schema_payload(frame,25,108)['payload_offset'],24)
        self.assertIsNone(schema_payload(b'not a real schema migration',25,108))
