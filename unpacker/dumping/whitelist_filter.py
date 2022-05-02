import hashlib
import json
import logging
import os

from utility.pe_tools import normalize_pe_header
from unpacker.winwrapper.utilities import read_memory, open_process, close_handle


class WhitelistFilter:
    def __init__(self, parent, additonal_white_list):
        self.parent = parent
        self.hash_table_path = "C:\\Users\\{}\\pe_header_whitelist.json".format(os.getenv("username"))
        self.dll_hash_table = self.update()
        self.dll_hash_table.update(additonal_white_list)
        self._filter_all = False

    def update(self):
        with open(self.hash_table_path, "r") as fIn:
            return json.loads(fIn.read())

    def _is_known_segment(self, header):
        header_hash = hashlib.sha256(header).hexdigest()
        for dll_name in self.dll_hash_table.keys():
            if header_hash in self.dll_hash_table[dll_name]:
                return True
        return False

    def _check_segment(self, segment, process_handle):
        header = read_memory(process_handle, segment.base_addr, 0x400)
        normalized_header = normalize_pe_header(header)
        return self._is_known_segment(normalized_header)

    def filter(self, tasks):
        known = set()
        filtered = []
        for task in tasks:
            process_handle = open_process(task.pid)
            if self._filter_all:
                for segment in task.segments:
                    if self._check_segment(segment, process_handle):
                        known.add(task)
                        break
            else:
                segment = task.segments[0]
                if self._check_segment(segment, process_handle):
                    known.add(task)
            close_handle(process_handle)
        filtered = list(set(tasks).difference(known))
        logging.info("removed %d/%d dump tasks according to whitelist.", len(tasks) - len(filtered), len(tasks))
        return filtered
