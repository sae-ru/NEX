"""Exercise actual provider streaming/range logic with bounded memory fixtures."""
from host_fixture import nonregular, sparse_file
import importlib.util
import sys
import types
import unittest
import time
import os
import struct
import tempfile
from pathlib import Path
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


class CoreImageMetadata(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex ELF metadata ')
        self.addCleanup(self.temp.cleanup)
        self.core = Path(self.temp.name) / 'process.core'

    def fixture(self, ranges, endian='<', terminate=True):
        paths = b'\0'.join(name.encode() for _, _, name in ranges) + (b'\0' if terminate else b'')
        data = struct.pack(endian+'QQ', len(ranges), 4096)
        data += b''.join(struct.pack(endian+'QQQ', begin, end, 0) for begin, end, _ in ranges) + paths
        note = struct.pack(endian+'III', 5, len(data), 0x46494c45) + b'CORE\0\0\0\0'
        note += data + bytes((-len(data)) % 4)
        ident = b'\x7fELF\x02' + bytes([1 if endian=='<' else 2, 1]) + bytes(9)
        header = struct.pack(endian+'16sHHIQQQIHHHHHH',ident,4,183,1,0,64,0,0,64,56,1,0,0,0)
        entry = struct.pack(endian+'IIQQQQQQ',4,0,120,0,0,len(note),len(note),4)
        self.core.write_bytes(header+entry+note)

    def test_recorded_path_and_both_byte_orders_without_reading_an_executable(self):
        path = '/absent/build/' + 'a'*64 + '/app'
        for endian in ('<','>'):
            self.fixture([(0x1000,0x2000,path),(0x3000,0x4000,'/other/module')],endian)
            self.assertEqual(provider._elf_core_mapping(str(self.core),0x1234),path)
            self.assertEqual(provider._elf_core_mapping(str(self.core),0x3000),'/other/module')

    def test_missing_ambiguous_relative_and_invalid_ranges_are_rejected(self):
        for ranges in [[],[(1,2,'/other')],[(0x1000,0x2000,'relative')],
                       [(0x1000,0x2000,'/a'),(0x1000,0x3000,'/b')],[(0x2000,0x1000,'/a')]]:
            with self.subTest(ranges=ranges),self.assertRaises(ValueError):
                self.fixture(ranges)
                provider._elf_core_mapping(str(self.core),0x1234)

    def test_truncated_headers_notes_tables_and_names_fail_closed(self):
        self.fixture([(0x1000,0x2000,'/app')]);valid=self.core.read_bytes()
        invalid = [b'x',valid[:63],valid[:119],valid[:-1]]
        altered=bytearray(valid);struct.pack_into('<H',altered,16,3);invalid.append(altered)
        altered=bytearray(valid);struct.pack_into('<H',altered,56,4097);invalid.append(altered)
        altered=bytearray(valid);struct.pack_into('<Q',altered,96,16*1024**2+1);invalid.append(altered)
        altered=bytearray(valid);struct.pack_into('<Q',altered,140,65537);invalid.append(altered)
        for data in invalid:
            with self.subTest(bytes=len(data)),self.assertRaises(ValueError):
                self.core.write_bytes(data);provider._elf_core_mapping(str(self.core),0x1234)
        self.fixture([(0x1000,0x2000,'/app')],terminate=False)
        with self.assertRaises(ValueError):provider._elf_core_mapping(str(self.core),0x1234)

    def test_nonregular_symlink_and_oversized_inputs_do_not_block(self):
        self.fixture([(0x1000,0x2000,'/app')])
        link=self.core.with_name('link');link.symlink_to(self.core)
        with self.assertRaises((OSError,ValueError)):provider._elf_core_mapping(str(link),0x1234)
        fifo=self.core.with_name('fifo');nonregular(fifo)
        with self.assertRaises(ValueError):provider._elf_core_mapping(str(fifo),0x1234)
        with self.core.open('wb') as stream:
            sparse_file(stream);stream.truncate(32*1024**3+1)
        with self.assertRaises(ValueError):provider._elf_core_mapping(str(self.core),0x1234)


if __name__=='__main__':unittest.main()
