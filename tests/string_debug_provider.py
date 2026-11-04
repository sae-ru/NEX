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
            sparse_file(stream,size=32*1024**3+1)
        with self.assertRaises(ValueError):provider._elf_core_mapping(str(self.core),0x1234)


class MinidumpImageMetadata(unittest.TestCase):
    BASE = 0x7ff633350000
    UUID = '11066e4ee008172f4c4c44205044422e00000001'
    NAME = 'F:\\absent\\build\\'+'a'*64+'\\app.exe'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex minidump metadata ')
        self.addCleanup(self.temp.cleanup)
        self.core = Path(self.temp.name)/'process.core'

    def fixture(self, records=None, duplicate_stream=False):
        records = records if records is not None else [(self.BASE, self.NAME, b'LEpB'+bytes.fromhex(self.UUID))]
        count = 2 if duplicate_stream else 1
        offset = 32+count*12
        size = 4+len(records)*108
        payload = bytearray()
        entries = bytearray()
        for base, name, cv in records:
            name_at = offset+size+len(payload)
            raw = name.encode('utf-16-le')
            payload.extend(struct.pack('<I', len(raw))+raw)
            cv_at = offset+size+len(payload)
            payload.extend(cv)
            record = bytearray(108)
            # Reproduce LLDB's PE header-only SizeOfImage; image identity is
            # bound by the actual module's load base and exact CodeView UUID.
            struct.pack_into('<QIIII', record, 0, base, 0x600, 0, 0, name_at)
            struct.pack_into('<II', record, 76, len(cv), cv_at)
            entries.extend(record)
        header = struct.pack('<4sIIIIIQ', b'MDMP', 0xa793, count, 32, 0, 0, 0)
        directory = struct.pack('<III', 4, size, offset)*count
        self.core.write_bytes(header+directory+struct.pack('<I',len(records))+entries+payload)

    def mapping(self, base=None, identity=None):
        return provider._minidump_core_mapping(str(self.core), self.BASE if base is None else base,
                                               self.UUID if identity is None else identity)

    def test_original_unicode_path_is_read_without_original_or_relocated_images(self):
        name = self.NAME.replace('absent', 'absent % 🧠')
        self.fixture([(self.BASE, name, b'LEpB'+bytes.fromhex(self.UUID))])
        before = self.core.read_bytes()
        self.assertEqual(self.mapping(identity=self.UUID.upper()), name)
        self.assertEqual(self.core.read_bytes(), before)
        posix = '/absent/build/'+'a'*64+'/app'
        self.fixture([(self.BASE, posix, b'LEpB'+bytes.fromhex(self.UUID))])
        self.assertEqual(self.mapping(), posix)

    def test_pdb70_guid_byte_order_and_zero_or_nonzero_age_match_lldb(self):
        guid = bytes.fromhex('00112233445566778899aabbccddeeff')
        wire = guid[:4][::-1]+guid[4:6][::-1]+guid[6:8][::-1]+guid[8:]
        for age in [0, 1, 0x12345678]:
            with self.subTest(age=age):
                self.fixture([(self.BASE, self.NAME, b'RSDS'+wire+struct.pack('<I',age)+b'ignored.pdb\0')])
                expected = guid.hex()+('%08x' % age if age else '')
                self.assertEqual(self.mapping(identity=expected), self.NAME)
                raw_identity = wire.hex()+(struct.pack('<I',age).hex() if age else '')
                self.assertEqual(provider._minidump_core_mapping(str(self.core),self.BASE,raw_identity,
                                                               pdb70_elf=True),self.NAME)

    def test_wrong_uuid_missing_base_duplicate_bases_and_invalid_identities_rejected(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError,'UUID differs'):self.mapping(identity='0'*40)
        with self.assertRaisesRegex(ValueError,'unique recorded module base'):self.mapping(base=self.BASE+0x1000)
        for identity in [self.UUID[:32], self.UUID+'00']:
            with self.subTest(recorded_uuid=identity),self.assertRaisesRegex(ValueError,'UUID differs'):
                self.fixture([(self.BASE,self.NAME,b'LEpB'+bytes.fromhex(identity))]);self.mapping()
        for base, identity in [(True,self.UUID),(0,self.UUID),(2**64,self.UUID),(self.BASE,''),
                               (self.BASE,'x'*40),(self.BASE,'a'),(self.BASE,False)]:
            with self.subTest(base=base,identity=identity),self.assertRaises(ValueError):
                provider._minidump_core_mapping(str(self.core),base,identity)
        self.fixture([(self.BASE,self.NAME,b'LEpB'+bytes.fromhex(self.UUID))]*2)
        with self.assertRaisesRegex(ValueError,'unique recorded module base'):self.mapping()
        self.fixture(duplicate_stream=True)
        with self.assertRaisesRegex(ValueError,'one minidump module list'):self.mapping()

    def test_truncated_and_unbounded_header_module_codeview_and_name_records_rejected(self):
        self.fixture();valid=self.core.read_bytes()
        invalid=[b'x',valid[:31],valid[:43],valid[:100],valid[:-1]]
        for at,fmt,value in [(0,'I',0),(4,'I',0),(8,'I',4097),(12,'I',2**32-1),
                             (36,'I',5),(40,'I',2**32-1),(44,'I',65537),
                             (48,'Q',0),(56,'I',0),(68,'I',2**32-1),
                             (124,'I',65537),(128,'I',2**32-1)]:
            changed=bytearray(valid);struct.pack_into('<'+fmt,changed,at,value);invalid.append(changed)
        for raw in invalid:
            with self.subTest(length=len(raw)),self.assertRaises(ValueError):
                self.core.write_bytes(raw);self.mapping()
        for cv in [b'OTHER',b'LEpB',b'LEpB'+b'a'*65,b'RSDS'+bytes(19)]:
            with self.subTest(cv=cv),self.assertRaises(ValueError):
                self.fixture([(self.BASE,self.NAME,cv)]);self.mapping()

    def test_invalid_utf16_nul_relative_and_oversized_names_rejected(self):
        for name in ['relative.exe',self.NAME+'\0','F:\\'+'a'*16385]:
            with self.subTest(name=name[:80]),self.assertRaises(ValueError):
                self.fixture([(self.BASE,name,b'LEpB'+bytes.fromhex(self.UUID))]);self.mapping()
        self.fixture();valid=self.core.read_bytes();name_at=struct.unpack_from('<I',valid,68)[0]
        for length in [0,1,32770,2**32-1]:
            changed=bytearray(valid);struct.pack_into('<I',changed,name_at,length)
            with self.subTest(length=length),self.assertRaises(ValueError):
                self.core.write_bytes(changed);self.mapping()
        changed=bytearray(valid);changed[name_at+4:name_at+6]=b'\x00\xd8';self.core.write_bytes(changed)
        with self.assertRaises(UnicodeDecodeError):self.mapping()

    def test_nonregular_symlink_oversized_and_metadata_deadline_are_rejected(self):
        self.fixture()
        link=self.core.with_name('link');link.symlink_to(self.core)
        with self.assertRaises((OSError,ValueError)):
            provider._minidump_core_mapping(str(link),self.BASE,self.UUID)
        original=provider.time.monotonic;counter=iter([0,3])
        try:
            provider.time.monotonic=lambda:next(counter)
            with self.assertRaisesRegex(ValueError,'bounds'):self.mapping()
        finally:provider.time.monotonic=original
        fifo=self.core.with_name('fifo');nonregular(fifo)
        with self.assertRaises(ValueError):provider._minidump_core_mapping(str(fifo),self.BASE,self.UUID)
        with self.core.open('wb') as stream:
            sparse_file(stream,size=32*1024**3+1)
        with self.assertRaises(ValueError):self.mapping()


if __name__=='__main__':unittest.main()
