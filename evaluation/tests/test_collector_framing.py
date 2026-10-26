"""OTLP body event IDs are counted independently of unrelated protobuf fields."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runner'))
from collector_cases import fields,log_event_ids


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
