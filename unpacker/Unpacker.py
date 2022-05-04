import logging
import os
import random
import time

from unpacker.dumping.dumper import Dumper
from unpacker.monitoring.monitor_manager import MonitorManager
from utility.pe_tools import check_if_library
from unpacker.winwrapper.user_interaction import UserInteractor
from unpacker.winwrapper.utilities import getUserPath, startAsLibrary, startAsExe


class Unpacker:

    def __init__(self, sample, config):
        self.sample = sample
        self.userPath = getUserPath()
        self.samplePath = os.path.join(self.userPath, "Desktop")
        
        self.fileType = self.determine_file_type(sample)

        self.sampleName = generate_random_samplename()
        logging.info("copying sample to: %s", os.path.join(self.samplePath, self.sampleName))
        with open(os.path.join(self.samplePath, self.sampleName), "wb") as fOut:
            fOut.write(self.sample)
        
        self.userInteractor = UserInteractor()
        self.timeTracker = TimeTracker()
        if "additional_pe_whitelist" in config.keys():
            additionalWhitelist = config["additional_pe_whitelist"]
        else:
            additionalWhitelist = {}
        self.dumper = Dumper(config["dump_filters"], additionalWhitelist, config["discard_reserved_segment_size"])
        self.sampleName = ""
        self.config = config
        self.monitoringIntervals = config["monitoring_intervals"]
        self.monitoringIntervalLength = config["monitoring_interval_length"]
        self.spoofUser = config["spoof_user"]
        self.monitorManager = MonitorManager(config["monitoring_switches"])

    def determine_file_type(self, sample):
        if check_if_library(sample):
            return "dll"
        return "exe"

    def starting_phase(self):
        self.dumper.update_filters()
        self.timeTracker.start_monitoring()
        time.sleep(self.config["sample_start_delay"])
        if self.fileType == "dll":
            startAsLibrary(os.path.join(self.samplePath, self.sampleName))
        else:
            startAsExe(self.config, self.userInteractor, self.samplePath, self.sampleName)
        time.sleep(1)

    def monitoring_phase(self):
        self._simulate_user_interaction(self.monitoringIntervalLength)
        for interval in range(self.monitoringIntervals):
            logging.info("iterated for the %d. time", interval + 1)
            start = time.time()
            self.monitorManager.track_changes(interval)
            end = time.time()
            if end - start < self.monitoringIntervalLength:
                logging.info("suspending for %s seconds (sleep or simulating user).",
                             self.monitoringIntervalLength - (end - start))
                self._simulate_user_interaction(self.monitoringIntervalLength - (end - start))
        self.timeTracker.end_monitoring()

    def _simulate_user_interaction(self, seconds):
        if self.config["spoof_user"]:
            self.userInteractor.simulate_user_interaction(seconds)
        else:
            time.sleep(seconds)

    def _collect_stats(self):
        stats = {
            "sample_name": self.sampleName,
            "is_dll": self.fileType
        }
        stats.update(self.timeTracker.collect_stats())
        stats.update(self.monitorManager.collect_stats())
        stats.update(self.dumper.collect_stats())
        return stats

    def get_output(self):
        self.timeTracker.start_extraction()
        logging.info("extracting relevant dumps")
        result = {}
        mem_map_changes = self.monitorManager.get_memory_map_changes()
        modules = self.monitorManager.get_modules()
        result["dumps"] = self.dumper.get_dumps(mem_map_changes, modules)
        self.timeTracker.end_extraction()
        result["stats"] = self._collect_stats()
        result["observations"] = self.monitorManager.collect_observations()
        return result


def generate_random_samplename():
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwyxz0123456789'
    return ''.join(random.choice(chars) for _ in range(random.randrange(7, 11))) + ".exe"


class TimeTracker:

    def __init__(self):
        self.begin_time_monitoring = 0
        self.end_time_monitoring = 0
        self.begin_time_extraction = 0
        self.end_time_extraction = 0

    def start_monitoring(self):
        self.begin_time_monitoring = time.time()

    def end_monitoring(self):
        self.end_time_monitoring = time.time()

    def start_extraction(self):
        self.begin_time_extraction = time.time()

    def end_extraction(self):
        self.end_time_extraction = time.time()

    def collect_stats(self):
        stats = {"begin_time_monitoring": self.begin_time_monitoring,
                 "end_time_monitoring": self.end_time_monitoring,
                 "begin_time_extraction": self.begin_time_extraction,
                 "end_time_extraction": self.end_time_extraction}
        return stats
