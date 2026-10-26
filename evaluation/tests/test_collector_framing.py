"""OTLP body event IDs are counted independently of unrelated protobuf fields."""
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from collector_cases import fields,log_event_ids
import collector_cases


def varint(value):
    output=bytearray()
    while value>127:output.append((value&127)|128);value>>=7
    return bytes(output)+bytes([value])


def field(number,value):return varint(number*8+2)+varint(len(value))+value


class CollectorFramingTest(unittest.TestCase):
    def test_only_actual_log_bodies_count_and_repeated_deliveries_stay_visible(self):
        marker=b'EVAL_OBS_EVENT_PILOT_FIXTURE_U1_N00001'
        record=field(5,field(1,marker))
        message=field(1,field(2,field(2,record)+field(2,record)))
        self.assertEqual(log_event_ids(message),[marker.decode(),marker.decode()])
        unrelated=field(1,field(1,marker))
        self.assertEqual(log_event_ids(unrelated),[])

    def test_truncated_and_overlong_frames_do_not_become_successful_empty_logs(self):
        for bad in [b'\x0a\x08short',b'\x80'*12,b'\x00',b'\x0f']:
            with self.assertRaises(ValueError):fields(bad)

    def test_native_metadata_restore_cannot_replace_the_logged_event_identity(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);addon=root/'addon';addon.mkdir();(addon/'package.json').write_text('{"version":"2026.10.7"}')
            snapshot=root/'native-state.sqlite';database=sqlite3.connect(str(snapshot));database.execute('create table owned_control(value text)');database.execute("insert into owned_control values ('original-native-metadata')");database.commit();database.close()
            template=root/'template.json';template.write_text(json.dumps(dict(native_state_snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),entry_configuration=dict(enabled=True))))
            with patch.object(collector_cases,'ADDON',addon),patch.object(collector_cases,'ADDON_TEMPLATE',template),patch.object(collector_cases,'ADDON_STATE',snapshot):
                config=collector_cases.configure(root/'case',4096,'PILOT_DISTINCT_TARGET_U1')
            self.assertNotIn('installs',config['plugins'])
            source=(root/'case/composition-a/index.js').read_text()
            self.assertIn('args.token==="PILOT_DISTINCT_TARGET_U1"?4096:8',source)
            restored=sqlite3.connect(str(root/'case/state/state/openclaw.sqlite'))
            self.assertEqual(restored.execute('select value from owned_control').fetchone()[0],'original-native-metadata');restored.close()
