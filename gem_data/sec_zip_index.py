"""Bounded streaming ZIP/ZIP64 directory reader for SEC archives.

Keeps only requested member metadata; never materializes the full directory
or a multi-gigabyte archive. Checked CRC, decompressed size, original CIK.
"""
from __future__ import annotations

import struct
import zlib

MAX_DIRECTORY = 150_000_000
MAX_MEMBERS = 2_000_000
MAX_MEMBER = 12_000_000
_MEMBER_CACHE = {}


class RemoteZipHold(ValueError):
    pass


class SelectedRemoteZip:
    def __init__(self, source, desired):
        self.source = source
        desired = set(desired)
        if len(desired) > 100:
            raise RemoteZipHold("Too many requested ZIP members")
        key = source.archive_id
        existing = _MEMBER_CACHE.get(key)
        if existing and desired.issubset(existing["searched"]):
            self.members = {name: existing["members"][name] for name in desired
                            if name in existing["members"]}
            return
        if existing:
            desired |= existing["searched"]
        self.members = {}
        tail_start = max(0, source.length-65557)
        source.seek(tail_start)
        tail = source.read(source.length-tail_start)
        i = tail.rfind(b"PK\x05\x06")
        if i < 0 or i+22 > len(tail):
            raise RemoteZipHold("ZIP end-of-central-directory missing")
        e = struct.unpack_from("<4s4H2IH", tail, i)
        count, size, offset = e[4], e[5], e[6]
        if count == 65535 or size == 0xffffffff or offset == 0xffffffff:
            j = tail.rfind(b"PK\x06\x07", 0, i)
            if j < 0 or j+20 > len(tail):
                raise RemoteZipHold("ZIP64 directory locator missing")
            _, disk, at, disks = struct.unpack_from("<4sIQI", tail, j)
            if disk != 0 or disks != 1:
                raise RemoteZipHold("Multi-disk ZIP unsupported")
            source.seek(at)
            record = source.read(56)
            if len(record) != 56:
                raise RemoteZipHold("ZIP64 directory record truncated")
            z = struct.unpack("<4sQHHIIQQQQ", record)
            if z[0] != b"PK\x06\x06":
                raise RemoteZipHold("ZIP64 directory record invalid")
            count, size, offset = z[7], z[8], z[9]
        if not (1 <= count <= MAX_MEMBERS and 1 <= size <= MAX_DIRECTORY
                and offset >= 0 and offset+size <= source.length):
            raise RemoteZipHold("SEC ZIP central directory exceeds safe limits")
        p, end = offset, offset+size
        for _ in range(count):
            if p+46 > end:
                raise RemoteZipHold("ZIP central directory truncated")
            source.seek(p)
            h = source.read(46)
            if len(h) != 46:
                raise RemoteZipHold("ZIP central header truncated")
            v = struct.unpack("<4s6H3I5H2I", h)
            if v[0] != b"PK\x01\x02":
                raise RemoteZipHold("ZIP central signature invalid")
            filename_len, extra_len, comment_len = v[10], v[11], v[12]
            p += 46+filename_len+extra_len+comment_len
            if p > end:
                raise RemoteZipHold("ZIP central entry overflow")
            name = source.read(filename_len)
            if name.isascii():
                label = name.decode("ascii")
                if label in desired:
                    self.members[label] = {
                        "crc": v[7], "size": v[9], "compressed": v[8],
                        "flags": v[3], "method": v[4], "offset": v[16],
                    }
            source.seek(p)
            if len(self.members) == len(desired):
                break
        _MEMBER_CACHE[key] = {"searched": desired, "members": self.members.copy()}

    def read_member(self, name):
        m = self.members.get(name)
        if m is None:
            raise KeyError("Selected CIK member not found in SEC ZIP")
        if (m["flags"] & 1 or m["method"] not in (0, 8)
                or m["size"] <= 0 or m["size"] > MAX_MEMBER
                or m["compressed"] > MAX_MEMBER
                or m["offset"] == 0xffffffff):
            raise RemoteZipHold("SEC ZIP selected member has unsupported encoding/size")
        s = self.source
        s.seek(m["offset"])
        hdr = s.read(30)
        if len(hdr) != 30:
            raise RemoteZipHold("ZIP selected member local header truncated")
        v = struct.unpack("<4s5H3I2H", hdr)
        if v[0] != b"PK\x03\x04" or v[3] != m["method"]:
            raise RemoteZipHold("ZIP selected member local header mismatch")
        filename = s.read(v[9])
        if filename != name.encode("ascii"):
            raise RemoteZipHold("ZIP selected member filename mismatch")
        s.seek(s.tell()+v[10])
        remaining = m["compressed"]
        dec = zlib.decompressobj(-15) if m["method"] == 8 else None
        output, total, checksum = [], 0, 0
        while remaining:
            buf = s.read(min(remaining, 262144))
            if not buf:
                raise RemoteZipHold("ZIP selected member truncated")
            remaining -= len(buf)
            part = dec.decompress(buf, MAX_MEMBER-total+1) if dec else buf
            total += len(part)
            if total > MAX_MEMBER:
                raise RemoteZipHold("ZIP selected member decompression limit")
            checksum = zlib.crc32(part, checksum)
            output.append(part)
        if dec:
            if not dec.eof or dec.unused_data or dec.unconsumed_tail:
                raise RemoteZipHold("ZIP selected member deflate incomplete")
            flushed = dec.flush()
            total += len(flushed)
            checksum = zlib.crc32(flushed, checksum)
            output.append(flushed)
        if total != m["size"] or (checksum & 0xffffffff) != m["crc"]:
            raise RemoteZipHold("ZIP selected member CRC/size mismatch")
        return b"".join(output)
