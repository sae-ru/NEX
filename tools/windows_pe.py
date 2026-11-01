"""Bounded PE/COFF image inspection without loading executable code.

Layout: https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
Only the supported 64-bit Windows image formats are accepted.
"""
import re
import struct
from pathlib import Path


def inspect(path):
    path=Path(path)
    if not path.is_file() or not 64<=path.stat().st_size<=512*1024**2:
        raise ValueError('missing or oversized PE image: '+str(path))
    data=path.read_bytes()
    def block(offset,size):
        if offset<0 or size<0 or offset+size>len(data):raise ValueError('truncated PE image: '+str(path))
        return data[offset:offset+size]
    def u16(offset):return struct.unpack('<H',block(offset,2))[0]
    def u32(offset):return struct.unpack('<I',block(offset,4))[0]
    if block(0,2)!=b'MZ':raise ValueError('expected PE DOS header: '+str(path))
    header=u32(0x3c)
    if header<64 or block(header,4)!=b'PE\0\0':raise ValueError('invalid PE signature')
    machine=u16(header+4);count=u16(header+6);optional=u16(header+20)
    if machine not in (0x8664,0xaa64) or not 1<=count<=96 or not u16(header+22)&2:
        raise ValueError('unsupported PE image machine/sections/characteristics')
    opt=header+24
    if optional<112 or u16(opt)!=0x20b:raise ValueError('expected a PE32+ optional header')
    block(opt,optional);sections=[]
    image_base=struct.unpack('<Q',block(opt+24,8))[0];headers=u32(opt+60)
    for index in range(count):
        offset=opt+optional+40*index;block(offset,40)
        virtual=u32(offset+8);rva=u32(offset+12);size=u32(offset+16);raw=u32(offset+20)
        if size:block(raw,size)
        sections.append((rva,max(virtual,size),raw,size))
    def offset(rva,size):
        matches=[raw+rva-start for start,span,raw,length in sections
                 if start<=rva and rva+size<=start+span and rva-start+size<=length]
        if 0<=rva and rva+size<=headers:matches.append(rva)
        if len(matches)!=1:raise ValueError('unmapped or ambiguous PE RVA')
        block(matches[0],size);return matches[0]
    def text(rva):
        # An import name is a bounded ASCII basename, never a search path.
        result=bytearray()
        for index in range(261):
            value=block(offset(rva+index,1),1)[0]
            if value==0:return result.decode('ascii')
            result.append(value)
        raise ValueError('unbounded PE name')
    directories=min(u32(opt+108),16)
    if 112+8*directories>optional:raise ValueError('truncated PE data directories')
    def directory(index):
        return (u32(opt+112+index*8),u32(opt+116+index*8)) if index<directories else (0,0)
    imports=set()
    def add(name):
        if not re.fullmatch(r'[A-Za-z0-9_+.-]{1,255}\.dll',name,re.I):
            raise ValueError('invalid PE dependency basename: '+name)
        imports.add(name.lower())
    for index,width,name_index in ((1,20,3),(13,32,1)):
        start,size=directory(index)
        if not start and not size:continue
        if not start or size<width or size>1024*1024:raise ValueError('invalid PE import directory')
        terminated=False
        for row in range(min(size//width,4097)):
            values=struct.unpack('<'+'I'*(width//4),block(offset(start+row*width,width),width))
            if not any(values):terminated=True;break
            if row>=4096:raise ValueError('PE import count exceeds bound')
            name=values[name_index]
            if index==13:
                if values[0] not in (0,1):raise ValueError('invalid delay-import attributes')
                if values[0]==0:name-=image_base
            add(text(name))
        if not terminated:raise ValueError('unterminated PE import directory')
    start,size=directory(0)
    if start or size:
        if not start or size<40:raise ValueError('invalid PE export directory')
        table=offset(start,40);functions=u32(table+20);addresses=u32(table+28)
        if functions>1024*1024:raise ValueError('PE export count exceeds bound')
        for index in range(functions):
            address=u32(offset(addresses+4*index,4))
            if start<=address<start+size:
                forward=text(address)
                if '.' not in forward:raise ValueError('invalid PE export forwarder')
                module=forward.rsplit('.',1)[0]
                add(module if module.lower().endswith('.dll') else module+'.dll')
    identity=None;start,size=directory(6)
    if start or size:
        if not start or size%28 or size>28*4096:raise ValueError('invalid PE debug directory')
        for index in range(size//28):
            entry=offset(start+index*28,28)
            if u32(entry+12)!=2:continue
            length=u32(entry+16);raw=u32(entry+24)
            if length<24:continue
            record=block(raw,length)
            if record[:4]!=b'RSDS':continue
            raw=record[4:20]
            guid=(raw[0:4][::-1]+raw[4:6][::-1]+raw[6:8][::-1]+raw[8:]+record[20:24][::-1]).hex()
            if guid[:32]=='0'*32 or identity not in (None,guid):raise ValueError('invalid or conflicting PE CodeView GUID')
            identity=guid
    return {'machine':'x86_64' if machine==0x8664 else 'arm64','imports':sorted(imports),'uuid':identity}


def image(path):
    with Path(path).open('rb') as source:magic=source.read(2)
    if magic!=b'MZ':return False
    inspect(path)
    return True


def system_directory():
    import ctypes as C
    from ctypes import wintypes as W
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes=[W.LPWSTR,W.UINT];kernel.GetSystemDirectoryW.restype=W.UINT
    buffer=C.create_unicode_buffer(32768);size=kernel.GetSystemDirectoryW(buffer,len(buffer))
    if not size or size>=len(buffer):raise C.WinError(C.get_last_error())
    return Path(buffer.value).resolve(strict=True)
