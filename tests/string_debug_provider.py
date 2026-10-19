"""Exercise actual provider streaming/range logic with bounded memory fixtures."""
import importlib.util
import sys
import types
import unittest
import time
path=sys.argv.pop(1)
sys.modules['lldb']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('string_range_provider',path);provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)


class Provider(unittest.TestCase):
    def setUp(self):
        self.reads=[]
        provider._string_layout=lambda value:(len(value),4096)
        def read(value,address,count):
            self.reads.append((address-4096,count));return value[address-4096:address-4096+count]
        provider._string_bytes=read

    def budget(self,**kw):return dict({'bytes':1048576,'scan_bytes':32*1048576,'deadline':time.monotonic()+10},**kw)

    def test_large_utf8_boundaries_length_nul_and_ranges(self):
        text=('A🌍\0λ'*300000)+'end';raw=text.encode();budget=self.budget();view=provider._TextView(raw,budget)
        self.assertEqual(view.length,len(text));self.assertEqual(view.range(32765,9),text[32765:32774]);self.assertEqual(view.range(len(text)-8,8),text[-8:])
        self.assertTrue(all(count<=65536 for _,count in self.reads));self.assertGreater(len(raw),1048576)
        self.assertLess(len(view.checkpoints),len(raw)//65536+3)

    def test_cache_reuses_scan_and_range_reads_begin_near_selected_chunk(self):
        raw=('🌍λA'*400000).encode();budget=self.budget();first=provider._TextView(raw,budget);before=len(self.reads);second=provider._TextView(raw,budget);self.assertEqual(len(self.reads),before)
        self.assertEqual(second.range(second.length-3,3),'🌍λA');self.assertLess(len(self.reads)-before,3)
        self.assertGreater(self.reads[-1][0],len(raw)-3*65536)

    def test_empty_and_exact_boundary_windows(self):
        view=provider._TextView(b'',self.budget());self.assertEqual(view.length,0);self.assertEqual(view.range(0,0),'');self.assertFalse(self.reads)
        raw=b'A'*65535+'🌍'.encode()+b'B'*65536;view=provider._TextView(raw,self.budget())
        self.assertEqual(view.range(65534,3),'A🌍B');self.assertEqual(view.range(view.length,0),'')

    def test_malformed_and_incomplete_utf8_tail_is_rejected_before_shape(self):
        for tail in [b'\xff',b'\xc0\xaf',b'\xed\xa0\x80',b'\xf0\x9f']:
            with self.subTest(tail=tail),self.assertRaises(UnicodeDecodeError):provider._TextView(b'A'*65535+tail,self.budget())

    def test_scan_and_output_budgets_are_separate_and_not_refunded_by_cache(self):
        raw=('🌍'*20000).encode();budget=self.budget(scan_bytes=len(raw)-1)
        with self.assertRaisesRegex(ValueError,'scan byte budget'):provider._TextView(raw,budget)
        self.assertFalse(self.reads)
        budget=self.budget(bytes=3);view=provider._TextView(raw,budget)
        with self.assertRaisesRegex(ValueError,'capture byte budget'):view.range(0,1)
        budget=self.budget(scan_bytes=len(raw));view=provider._TextView(raw,budget)
        with self.assertRaisesRegex(ValueError,'scan byte budget'):view.range(0,1)

    def test_deadline_and_out_of_bounds_reject_without_target_evaluation(self):
        with self.assertRaisesRegex(ValueError,'deadline'):provider._TextView(b'A',self.budget(deadline=0))
        view=provider._TextView(b'hello',self.budget())
        for start,count in [(-1,1),(0,-1),(5,1),(6,0),(0,4097)]:
            with self.subTest(start=start,count=count),self.assertRaises(ValueError):view.range(start,count)

    def test_changed_buffer_cannot_bypass_utf8_validation_on_selected_range(self):
        value=b'A'*70000;view=provider._TextView(value,self.budget());view.value=b'A'*69999+b'\xff'
        with self.assertRaises(ValueError):view.range(69999,1)


if __name__=='__main__':unittest.main()
