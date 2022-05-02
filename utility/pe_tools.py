import re
import struct

import os

_THIS_PATH = os.path.dirname(os.path.realpath(__file__))

MAGIC_PE_32      = 0x010b
MAGIC_PE_32_PLUS = 0x020b 

def _extractPEMagic(data, pe_offset):
    bitness_magic = 0
    if len(data) >= pe_offset + 0x1A:
        bitness_magic = struct.unpack("H", data[pe_offset+0x18:pe_offset+0x1A])[0]
    return bitness_magic


def _is_dotnet(data, pe_offset, is_64_bit):
    clr_entry_offset = 0xE8 + (0x10 if is_64_bit else 0)
    clr_entry = data[pe_offset+clr_entry_offset: pe_offset+clr_entry_offset+8]
    return any(clr_entry)


def iterate_pe_headers(data):
    header_candidates = re.finditer(b"\x4D\x5A", data)
    for candidate in header_candidates:
        candidate_offset = candidate.start(0)
        optional_header_pointer = candidate_offset + int(0x3c)
        try:
            optional_header_start = candidate_offset + struct.unpack("I", data[optional_header_pointer:optional_header_pointer + 4])[0]
        except struct.error:
            continue
        # NOTE: Slicing with a to large endpoint will NEVER cause an exception.
        if data[optional_header_start:optional_header_start + 2] == b"PE":
            yield candidate_offset, optional_header_start


def normalize_pe_header(data_raw):
    candidate_offset, pe_offset_shifted = None, None
    for candidate_offset, pe_offset_shifted in iterate_pe_headers(data_raw):
        break
    if candidate_offset is None or pe_offset_shifted is None: # no PE Header found
        return data_raw
    pe_magic = _extractPEMagic(data_raw, pe_offset_shifted)
    if pe_magic not in (MAGIC_PE_32, MAGIC_PE_32_PLUS):          # invalid PE magic
        return data_raw[candidate_offset:candidate_offset+0x200]
    # PE Header with valid magic found
    is_64_bit = (pe_magic == MAGIC_PE_32_PLUS)
    num_sections = struct.unpack("H", data_raw[pe_offset_shifted + 6:pe_offset_shifted + 8])[0]
    end_pointer = pe_offset_shifted + 0xf8 + num_sections * 0x28 + (0x10 if is_64_bit else 0)
    # Cut Data
    data = bytearray(data_raw[candidate_offset:end_pointer])
    pe_offset = pe_offset_shifted - candidate_offset
    #
    # Native Executables:
    if not _is_dotnet(data, pe_offset, is_64_bit):
        if is_64_bit: 
            masks = [(0x30, 0x38)]  #Mask ImageBase, 64 bit
        else: #32 bit
            masks = [(0x34, 0x38)]  #Mask ImageBase
    else:  # .NET executable
        if is_64_bit:
            # 'convert' to 32 bit
            for expanded_entry_offset in 0x78, 0x70, 0x68, 0x60:
                del data[pe_offset+expanded_entry_offset+4:pe_offset+expanded_entry_offset+8]
            # change Optional header magic 64 -> 32
            data[pe_offset+0x18:pe_offset+0x1A] = struct.pack("H", MAGIC_PE_32)
            # decrease size of optional header by 16
            old_optional_header_size = struct.unpack("H", data[pe_offset+0x14:pe_offset+0x16])[0]
            data[pe_offset+0x14:pe_offset+0x16] = struct.pack("H", old_optional_header_size-0x10)
        # mask is for 32 and 64 bit, since we have already converted
        masks = [
            (0x30, 0x38),  #Mask ImageBase, 64 bit / ImageBase + BaseOfData
            (0x28, 0x2C),  #Mask Entrypoint
            (0x80, 0x88),  #Mask IAT
            (0xD8, 0xE0),  #Mask IT
        ]
    for mask in masks:
        data[pe_offset+mask[0]:pe_offset+mask[1]] = bytearray(mask[1]-mask[0])
    return data


def checkMzHeaderInDump(dump):
    for _ in iterate_pe_headers(dump):
        return True
    return False


def check_if_library(data):
    for _, pe_offset in iterate_pe_headers(data):
        try:
            characteristics = struct.unpack("I", data[pe_offset + 22: pe_offset + 26])[0]
        except struct.error:
            continue
        bitmask = characteristics & 0x2000
        if int(bitmask) == 0x2000:
            return True
    return False
