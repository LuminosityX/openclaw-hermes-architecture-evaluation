"""Privacy fixtures distinguish valid binary input and retained owner backups."""
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from privacy_cases import png_canary,sqlite_contains,stored_canary_locations


class PrivacyFixtureTest(unittest.TestCase):
    def test_attachment_is_a_crc_valid_png_with_a_distinct_metadata_canary(self):
        data=png_canary('AttachmentCanary_test');self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
        position=8;kinds=[]
        while position<len(data):
            size=struct.unpack('!I',data[position:position+4])[0];kind=data[position+4:position+8]
            body=data[position+8:position+8+size];crc=struct.unpack('!I',data[position+8+size:position+12+size])[0]
            self.assertEqual(crc,zlib.crc32(kind+body)&0xffffffff);kinds.append(kind)
            if kind==b'IDAT':self.assertEqual(len(zlib.decompress(body)),5)
            position+=12+size
        self.assertEqual(kinds,[b'IHDR',b'tEXt',b'IDAT',b'IEND'])
        self.assertIn(b'AttachmentCanary_test',data)

    def test_wal_aware_backup_retains_a_canary_after_live_deletion(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'live.sqlite';backup=root/'backup.sqlite'
            live=sqlite3.connect(str(path));live.execute('pragma journal_mode=wal');live.execute('create table transcript(content text)')
            live.execute('insert into transcript values (?)',('PrivateCanaryIndependent',));live.commit()
            target=sqlite3.connect(str(backup));live.backup(target);target.close()
            live.execute('delete from transcript');live.commit();live.close()
            self.assertFalse(sqlite_contains(path,'PrivateCanaryIndependent'))
            self.assertTrue(sqlite_contains(backup,'PrivateCanaryIndependent'))
            self.assertIn('backup.sqlite',stored_canary_locations(root,'PrivateCanaryIndependent')['uncompressed_exact_byte_matches'])
