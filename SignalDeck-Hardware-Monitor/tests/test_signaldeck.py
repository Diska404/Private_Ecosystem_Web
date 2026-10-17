"""Run with: python -m unittest discover -s tests -v"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector import HardwareCollector, gpu_name_matches
from librehardware import parse_value
from storage import HistoryStore,flatten_snapshot


class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector=HardwareCollector(demo=True)

    def test_demo_explicitly_labeled(self):
        snap=self.collector.collect()
        self.assertTrue(snap['demo'])
        self.assertEqual(len(snap['gpus']),3)
        self.assertIn('RTX 5070',snap['gpus'][1]['name'])
        self.assertIn('Intel UHD',snap['gpus'][2]['name'])
        self.assertGreater(snap['memory']['total_bytes'],0)
        self.assertGreater(len(snap['sensors']),20)
        json.dumps(snap,allow_nan=False)

    def test_nvidia_and_intel_name_matching(self):
        self.assertTrue(gpu_name_matches('NVIDIA GeForce RTX 5070','GPU NVIDIA GeForce RTX 5070'))
        self.assertTrue(gpu_name_matches('Intel(R) UHD Graphics','GPU Intel UHD Graphics'))
        self.assertFalse(gpu_name_matches('Intel UHD Graphics','NVIDIA GeForce RTX 5070'))

    def test_value_parsing(self):
        self.assertEqual(parse_value('48.5 °C'),(48.5,'°C'))
        self.assertEqual(parse_value('1,520 RPM'),(1520.0,'RPM'))
        self.assertEqual(parse_value('2.3 GHz'),(2.3,'GHz'))
        self.assertEqual(parse_value('not available'),None)


class DatabaseTests(unittest.TestCase):
    def test_history_aggregation_and_export(self):
        with tempfile.TemporaryDirectory() as d:
            history=HistoryStore(Path(d)/'samples.db')
            collector=HardwareCollector(demo=True)
            for i in range(12):
                sample=collector.collect()
                sample['timestamp']=time.time()-40+i*2
                history.record(sample)
            self.assertTrue(history.get_history('live')['count']>=10)
            self.assertGreaterEqual(history.get_history('7d')['count'],1)
            self.assertGreaterEqual(history.get_history('365d')['count'],1)
            out=history.export_csv('24h')
            self.assertIn('cpu',out)
            self.assertIn('gpu.nvidia-1.load',out)
            self.assertIn('ts',out)

    def test_missing_sensor_values_not_fabricated(self):
        collector=HardwareCollector(demo=True)
        snap=collector.collect()
        snap['gpus'][0]['temperature_c']=None
        data=flatten_snapshot(snap)
        self.assertNotIn('gpu.nvidia-0.temp',data)


if __name__=='__main__':
    unittest.main()
