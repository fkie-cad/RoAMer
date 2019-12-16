import hashlib
import json
import os
import re
import struct
import sys


def hexdump(src, length=32, indent=0):
    """
    source : http://pastebin.com/C3XszsCv
    """
    trans_table = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])
    lines = []
    for c in range(0, len(src), length):
        chars = src[c:c + length]
        hexed = ' '.join(["%02x" % ord(x) for x in chars])
        printable = ''.join(["%s" % ((ord(x) <= 127 and trans_table[ord(x)]) or '.') for x in chars])
        lines.append("%s%04x  %-*s  %s\n" % (indent * " ", c, length * 3, hexed, printable))
    return ''.join(lines)


class PeHeaderWhitelister(object):

    target_extensions = [".dll", ".exe", ".drv", ".DLL", ".pyd", ".PYD", ".cpl", "conhost", ".mui", ".MUI", ".EXE"]

    def __init__(self):
        self.hashed_pe_headers = {}

    def read_pe_header_from_file(self, path):
        try:
            with open(path, "rb") as f_in:
                return f_in.read(0x400)
        except OSError:
            print("could not read ", path, "... continuing")

    def _extractBitnessMagic(self, data, pe_offset):
        bitness_magic = 0
        if len(data) >= pe_offset + 6:
            bitness_magic = struct.unpack("H", data[pe_offset + 4:pe_offset + 6])[0]
        return bitness_magic

    def normalize_pe_header(self, data):
        normalized_pe_header = data
        header_candidates = re.finditer(b"\x4D\x5A", data)
        for candidate in header_candidates:
            candidate_offset = candidate.start(0)
            optional_header_pointer = candidate_offset + int(0x3c)
            try:
                optional_header_start = struct.unpack("I", data[optional_header_pointer:optional_header_pointer + 4])[0]
            except struct.error:
                continue
            if data[optional_header_start:optional_header_start + 2] == b"PE":
                num_sections = struct.unpack("H", data[optional_header_start + 6:optional_header_start + 8])[0]
                end_pointer = 0x200
                if self._extractBitnessMagic(data, optional_header_start) == 0x14c:
                    normalized_pe_header = data[:optional_header_start + 0x34] + b"\x00" * 4 + data[
                                                                                               optional_header_start + 0x38:]
                    end_pointer = optional_header_start + 0xf8 + num_sections * 0x28
                elif self._extractBitnessMagic(data, optional_header_start) == 0x8664:
                    normalized_pe_header = data[:optional_header_start + 0x30] + b"\x00" * 8 + data[
                                                                                               optional_header_start + 0x38:]
                    end_pointer = optional_header_start + 0x108 + num_sections * 0x28
                normalized_pe_header = normalized_pe_header[:end_pointer]
        return normalized_pe_header

    def add_entry(self, root, filename):
        header = self.normalize_pe_header(self.read_pe_header_from_file(os.path.join(root, filename)))
        file_entry = self.hashed_pe_headers.get(filename.lower(), [])
        hashed_header = hashlib.sha256(header).hexdigest()
        if hashed_header not in file_entry:
            file_entry.append(hashed_header)
        self.hashed_pe_headers[filename.lower()] = file_entry

    def generate_pe_header_whitelist(self, path):
        for root, _, filenames in os.walk(path):
            for filename in filenames:
                _, extension = os.path.splitext(filename)
                if extension in self.target_extensions:
                    self.add_entry(root, filename)
        return self.hashed_pe_headers

    def store_whitelist(self, filename="pe_header_whitelist.json"):
        with open(filename, "w") as f_out:
            f_out.write(json.dumps(self.hashed_pe_headers, indent=1, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        WHITELISTER = PeHeaderWhitelister()
        whitelist = WHITELISTER.generate_pe_header_whitelist(sys.argv[1])
        WHITELISTER.store_whitelist()

