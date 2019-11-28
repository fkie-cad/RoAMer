import logging

from unpacker.monitoring.memorymap_monitor import MemorymapMonitor
from unpacker.monitoring.modules_monitor import ModulesMonitor


class MonitorManager:
    def __init__(self, requested_monitors):
        self.initiate_monitors(requested_monitors)

    def initiate_monitors(self, additional_monitors):
        logging.info("initiating monitors: [%s]", ",".join(additional_monitors))
        self.memorymap_monitor = MemorymapMonitor()
        self.modules_monitor = ModulesMonitor()
        self.monitors = [self.memorymap_monitor, self.modules_monitor]
        for switch in additional_monitors:
            if switch == "dummy":
                self.monitors.append(None)

    def track_changes(self, interval):
        for monitor in self.monitors:
            monitor.track_changes(interval)

    def get_memory_map_changes(self):
        return self.memorymap_monitor.get_memory_map_changes()

    def get_modules(self):
        return self.modules_monitor.get_modules()

    def collect_observations(self):
        observations = {
            "first_snapshot": [],
            "latest_snapshot": [],
            "latest_changes": []
        }
        for monitor in self.monitors:
            observations["first_snapshot"].append(monitor.get_first_snapshot())
            observations["latest_snapshot"].append(monitor.get_latest_snapshot())
            observations["latest_changes"].append(monitor.get_latest_changes())
        return observations

    def collect_stats(self):
        stats = {
            "changes": []
        }
        for monitor in self.monitors:
            stats["changes"].append(monitor.get_change_summary())
        return stats
