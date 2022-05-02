import argparse
import hashlib
import os
import sys

WHITELISTER_FOLDER_PATH = str(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = str(os.path.abspath(os.sep.join([WHITELISTER_FOLDER_PATH, ".."])))

sys.path.append(PROJECT_ROOT)
from utility.pe_tools import normalize_pe_header


def read_pe_header_from_file(path):
    try:
        with open(path, "rb") as f_in:
            return f_in.read(0x400)
    except OSError:
        print("could not read ", path, "... continuing")
        return b""

def get_hashed_header_from_file(path):
    header = normalize_pe_header(read_pe_header_from_file(path))
    hashed_header = hashlib.sha256(header).hexdigest()
    return hashed_header

def print_hashes(filenames):
    for filename in filenames:
        if os.path.isdir(filename):
            print(f"{filename}: Is a directory", file=sys.stderr)
            continue
        print(get_hashed_header_from_file(filename), " ", filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='PeHeaderHasher')
    parser.add_argument('Paths', type=str, nargs='+', help='Files to calculate hash for')
    args = parser.parse_args()

    print_hashes(args.Paths)
