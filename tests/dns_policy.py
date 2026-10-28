"""Reject malformed operator authority before SDK work or network access."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/'tools/dns_provider/verify_delivery.py'
spec=importlib.util.spec_from_file_location('dns_delivery',path)
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)

class Policy(unittest.TestCase):
    def test_policy_is_strict_regular_bounded_and_explicit(self):
        with tempfile.TemporaryDirectory(prefix='nex-dns-policy-') as directory:
            rows=delivery.check_policy_rejections(Path(directory))
            self.assertEqual(len(rows),33)
            self.assertEqual(len({v['case'] for v in rows}),len(rows))

if __name__=='__main__':unittest.main()
