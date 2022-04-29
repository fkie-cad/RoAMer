import argparse
import hashlib
import json
import os
import sys

WHITELISTER_FOLDER_PATH = str(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = str(os.path.abspath(os.sep.join([WHITELISTER_FOLDER_PATH, ".."])))

sys.path.append(PROJECT_ROOT)
from utility.pe_tools import normalize_pe_header

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
            return b""

    def add_entry(self, root, filename):
        header = normalize_pe_header(self.read_pe_header_from_file(os.path.join(root, filename)))
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
    parser = argparse.ArgumentParser(description='PeHeaderWhitelister')
    parser.add_argument('Path', type=str, help='Root-path for whitelisting')
    args = parser.parse_args()

    if os.path.exists(args.Path):
        WHITELISTER = PeHeaderWhitelister()
        whitelist = WHITELISTER.generate_pe_header_whitelist(args.Path)
        WHITELISTER.store_whitelist()
    else:
        print("Error: Path does not exist")
