import re
import struct

import os

_THIS_PATH = os.path.dirname(os.path.realpath(__file__))


def _extractBitnessMagic(data, pe_offset):
    bitness_magic = 0
    if len(data) >= pe_offset + 6:
        bitness_magic = struct.unpack("H", data[pe_offset+4:pe_offset+6])[0]
    return bitness_magic


def iterate_pe_headers(data):
    header_candidates = re.finditer(b"\x4D\x5A", data)
    for candidate in header_candidates:
        candidate_offset = candidate.start(0)
        optional_header_pointer = candidate_offset + int(0x3c)
        try:
            optional_header_start = candidate_offset + struct.unpack("I", data[optional_header_pointer:optional_header_pointer + 4])[0]
        except struct.error:
            continue
        if data[optional_header_start:optional_header_start + 2] == b"PE":
            yield candidate_offset, optional_header_start


def normalize_pe_header(data):
    normalized_pe_header = data
    for candidate_offset, optional_header_start in iterate_pe_headers(data):
        num_sections = struct.unpack("H", data[optional_header_start + 6:optional_header_start + 8])[0]
        end_pointer = candidate_offset + 0x200
        if _extractBitnessMagic(data, optional_header_start) == 0x14c:
            normalized_pe_header = data[:optional_header_start + 0x34] + b"\x00" * 4 + data[optional_header_start + 0x38:]
            end_pointer = optional_header_start + 0xf8 + num_sections * 0x28
        elif _extractBitnessMagic(data, optional_header_start) == 0x8664:
            normalized_pe_header = data[:optional_header_start + 0x30] + b"\x00" * 8 + data[optional_header_start + 0x38:]
            end_pointer = optional_header_start + 0x108 + num_sections * 0x28
        normalized_pe_header = normalized_pe_header[candidate_offset:end_pointer]
        break
    return normalized_pe_header


def checkMzHeaderInDump(dump):
    iteration = re.finditer(b"\x4D\x5A", dump)
    locations = [m.start(0) for m in iteration]
    for location in locations:
        pe_location = location + int(0x3c)
        if (pe_location + 3) >= len(dump):
            continue
        try:
            offset = struct.unpack("I", dump[pe_location:pe_location+4])[0]
        except struct.error:
            continue
        if (location + offset + 1) >= len(dump):
            continue
        if dump[location + offset:location + offset + 2] == "\x50\x45":
            return True
        else:
            continue
    return False


def check_if_library(data):
    iteration = re.finditer(b"\x4D\x5A", data)
    locations = [m.start(0) for m in iteration]
    for location in locations:
        pe_location = location + int(0x3c)
        try:
            offset = struct.unpack("I", data[pe_location:pe_location + 4])[0]
        except IndexError:
            continue
        if (offset + 22 + 4) >= len(data):
            continue
        if data[offset:offset + 2] == b"PE":
            try:
                characteristics = struct.unpack("I", data[offset + 22: offset + 26])[0]
            except struct.error:
                continue
            bitmask = characteristics & 0x2000
            if int(bitmask) == 0x2000:
                return True
    return False
