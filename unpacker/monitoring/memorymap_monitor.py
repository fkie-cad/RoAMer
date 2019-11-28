import time
from collections import defaultdict

from unpacker.winwrapper import utilities


class MemorymapMonitor:

    def __init__(self):
        self.current_memory_map = None
        self.first_snapshot = None
        self.generate_memorymap_snapshot()
        self.changes_memorymaps = {}

    def get_new_memory_maps(self):
        return utilities.returnMemorymapForAllProcesses()

    def generate_memorymap_snapshot(self):
        self.current_memory_map = self.get_new_memory_maps()
        if not self.first_snapshot:
            self.first_snapshot = self.current_memory_map

    def track_changes(self, interval=0):
        memorymap_reference = self.current_memory_map
        self.generate_memorymap_snapshot()
        for pid in self.current_memory_map:
            if pid in memorymap_reference.keys():
                changes = list(self.current_memory_map[pid].difference(memorymap_reference[pid]))
            else:
                changes = list(self.current_memory_map[pid])
            if pid not in self.changes_memorymaps:
                self.changes_memorymaps[pid] = []
            for change in changes:
                change = list(change)
                change.append(time.time())
                change = tuple(change)
                self.changes_memorymaps[pid].append(change)
        return

    def get_memory_map_changes(self):
        mem_map = defaultdict(list)
        for mm_pid in self.changes_memorymaps:
            for segment in self.changes_memorymaps[mm_pid]:
                if not (mm_pid, segment[0]) in mem_map:
                    mem_map[mm_pid].append(segment[0])
        return mem_map

    def get_first_snapshot(self):
        output = {}
        for pid in self.first_snapshot:
            output[pid] = list(self.first_snapshot[pid])
        return {"memorymap_first": output}

    def get_latest_snapshot(self):
        output = {}
        for pid in self.current_memory_map:
            output[pid] = list(self.current_memory_map[pid])
        return {"memorymap_latest": output}

    def get_latest_changes(self):
        return {"memorymap_latest_changes": self.changes_memorymaps}

    def get_change_summary(self):
        return {"memorymap_change_summary": [pid for pid in self.changes_memorymaps if self.changes_memorymaps[pid]]}
