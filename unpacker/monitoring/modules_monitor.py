import json
import logging
import os
from collections import defaultdict

from unpacker.winwrapper import utilities
from utility.win_env import get_user_path


class ModulesMonitor:
    def __init__(self):
        whitelist_path = os.path.join(*[get_user_path(), "pe_header_whitelist.json"])
        with open(whitelist_path, "r") as f_in:
            self.dll_hash_table = json.loads(f_in.read())
        logging.info("loaded %d PE header whitelist entries", len(self.dll_hash_table))
        self.current_snapshot = None
        self.first_snapshot = None
        self.generate_modules_snapshot()
        self.changes_modules = {}

    def generate_modules_snapshot(self):
        self.current_snapshot = utilities.getAllModules()
        if not self.first_snapshot:
            self.first_snapshot = self.current_snapshot

    def _get_modules_for_name(self, name):
        for pid in self.current_snapshot.keys():
            if self.current_snapshot[pid]["name"] == name:
                return {
                    pid: {"name": name, "modules": self.current_snapshot[pid]["modules"]}
                }
        return {None: {"name": name, "modules": set()}}

    def track_changes(self, interval=0):
        self.generate_modules_snapshot()
        modules_reference = self.current_snapshot
        self.generate_modules_snapshot()
        for pid in self.current_snapshot:
            if pid in modules_reference.keys():
                changes = list(
                    self.current_snapshot[pid].difference(modules_reference[pid])
                )
            else:
                changes = list(self.current_snapshot[pid])
            if pid not in self.changes_modules:
                self.changes_modules[pid] = []
            for change in changes:
                self.changes_modules[pid].append(change)
        return

    def get_modules(self):
        candidates = defaultdict(list)
        all_modules = utilities.getAllModules()
        for pid in all_modules:
            for module in all_modules[pid]:
                candidates[pid].append((module[1][0], module[1][1]))
        return dict(candidates)

    def get_first_snapshot(self):
        output = {}
        for pid in self.first_snapshot:
            output[pid] = list(self.first_snapshot[pid])
        return {"modules_first": output}

    def get_latest_snapshot(self):
        output = {}
        for pid in self.current_snapshot:
            output[pid] = list(self.current_snapshot[pid])
        return {"modules_latest": output}

    def get_latest_changes(self):
        return {"modules_latest_changes": self.changes_modules}

    def get_change_summary(self):
        return {
            "modules_change_summary": sorted(
                [pid for pid in self.changes_modules if self.changes_modules[pid]]
            )
        }
