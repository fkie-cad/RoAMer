import logging
from base64 import b64encode
from collections import Counter
import os

from unpacker.dumping.dump_task import DumpTask
from unpacker.dumping.mapped_memory_filter import MappedMemoryFilter
from unpacker.dumping.memmap_change_filter import MemMapChangeFilter
from unpacker.dumping.only_executable_filter import OnlyExecutableFilter
from unpacker.dumping.only_executable_or_pe_header_filter import OnlyExecutableOrPeHeaderFilter
from unpacker.dumping.only_pe_header_filter import OnlyPeHeaderFilter
from unpacker.dumping.whitelist_filter import WhitelistFilter
from utility import pe_tools
from unpacker.winwrapper.utilities import return_memory_map_for_pid, open_process, read_memory, close_handle, name_of_process


class Dumper:

    def __init__(self, filter_names, additonal_white_list, discard_reserved_segment_size):
        self.filters = self.initiate_filters(filter_names, additonal_white_list)
        self.stats = {"dumper": {}}
        self.dump_task_cases = Counter()
        self.mem_map_changes = {}
        self.modules = {}
        self.additonal_white_list = additonal_white_list
        self.discard_reserved_segment_size = discard_reserved_segment_size

    def initiate_filters(self, filter_names, additonal_white_list):
        filters = []
        for filterName in filter_names:
            if filterName == "pe_header_whitelist":
                filters.append(WhitelistFilter(self, additonal_white_list))
            elif filterName == "memmap_change":
                filters.append(MemMapChangeFilter(self))
            elif filterName == "mapped_memory":
                filters.append(MappedMemoryFilter(self))
            elif filterName == "only_executable_filter":
                filters.append(OnlyExecutableFilter(self))
            elif filterName == "only_executable_or_pe_header_filter":
                filters.append(OnlyExecutableOrPeHeaderFilter(self))
            elif filterName == "only_pe_header_filter":
                filters.append(OnlyPeHeaderFilter(self))
        return filters

    def update_filters(self):
        for f in self.filters:
            f.update()

    def _calculate_stats_for_tasks(self, tasks):
        num_segments = 0
        mem_size = 0
        for task in tasks:
            num_segments += task.get_num_segments()
            mem_size += task.get_total_memory_size()
        return {"num_tasks": len(tasks), "num_segments": num_segments, "total_memory_size": mem_size}
    
    def _add_stats_for_tasks(self, dict1, dict2):
        for key in dict1:
            dict1[key] += dict2[key]

    def _calculate_stats_for_dump(self, dumps):
        num_dummies = 0
        num_inconsistent_segments = 0
        mem_size = 0
        for fields in dumps:
            for segment in fields["segments"]:
                if segment["isdummy"]:
                    num_dummies += 1
                if segment["size"] != segment["dumped_size"]:
                    num_inconsistent_segments += 1
                mem_size += len(segment["dump"])
        return {"num_dummies": num_dummies, "num_inconsistent_segments": num_inconsistent_segments,
                "total_memory_size": mem_size}

    def get_dumps(self, mem_map_changes, modules):
        self.mem_map_changes = mem_map_changes
        self.modules = modules
        logging.info("Creating dump tasks for own pid")
        #TODO: will update work here?
        dump_tasks_own = self._create_dump_tasks(mem_map_changes, modules, True)
        self.stats["dumper"]["initial_tasks"] = self._calculate_stats_for_tasks(dump_tasks_own)
        logging.info("Filtering dump tasks for own pid")
        filtered_own = self._filter_tasks(dump_tasks_own)
        self.stats["dumper"]["filtered_tasks"] = self._calculate_stats_for_tasks(filtered_own)

        logging.info("Creating dump tasks for other pids")
        dump_tasks_other = self._create_dump_tasks(mem_map_changes, modules, False)
        self._add_stats_for_tasks(self.stats["dumper"]["initial_tasks"], self._calculate_stats_for_tasks(dump_tasks_other))
        logging.info("Filtering dump tasks for other pids")
        filtered_other = self._filter_tasks(dump_tasks_other)
        self._add_stats_for_tasks(self.stats["dumper"]["filtered_tasks"], self._calculate_stats_for_tasks(filtered_other))

        logging.info("Dumping remaining tasks")
        dumped = self._dump(filtered_own+filtered_other)
        self.stats["dumper"]["dumped"] = self._calculate_stats_for_dump(dumped)
        self.stats["dumper"]["task_creation"] = dict(self.dump_task_cases)
        return dumped

    def _filter_tasks(self, tasks):
        filtered = tasks
        for task_filter in self.filters:
            filtered = task_filter.filter(filtered)
        return filtered

    def _create_dump_task(self, pid, segment, current_modules):
        dump_task = DumpTask(pid, segment)
        for module in current_modules:
            if dump_task.get_base_address() == module[0]:
                dump_task.set_module(module)
        return dump_task

    def _check_address_is_module_start(self, addr, current_modules):
        return addr in [m[0] for m in current_modules]

    def _create_dump_tasks(self, mem_map_changes, modules, for_own_pid):
        own_pid = os.getpid()
        tasks = []
        if for_own_pid:
            pids_of_interest = (own_pid,)
        else:
            pids_of_interest = list(set(mem_map_changes.keys()) - set((own_pid,)))
        for pid in sorted(pids_of_interest):
            dump_task = None
            current_modules = modules[pid] if pid in modules else []
            sorted_segments = sorted(list(return_memory_map_for_pid(pid)[pid]), key=lambda x: x[0])
            if len(sorted_segments) > 1:
                for index, segment in enumerate(sorted_segments):
                    if not dump_task:
                        self.dump_task_cases["no_dump_task"] += 1
                        dump_task = self._create_dump_task(pid, segment, current_modules)
                    else:
                        if dump_task.is_in_own_module_range(segment[0]):
                            self.dump_task_cases["segment_in_module"] += 1
                            dummy_address = dump_task.get_current_top_address()
                            dummy_size = segment[0] - dummy_address
                            if dummy_size:
                                dump_task.add_dummy_segment(dummy_address, dummy_size)
                            dump_task.add_segment(segment)
                        elif dump_task.get_current_top_address() == segment[0]:
                            process_handle = open_process(pid)
                            segment_start = read_memory(process_handle, segment[0], 0x400)
                            close_handle(process_handle)
                            if self._check_address_is_module_start(segment[0], current_modules):
                                self.dump_task_cases["consecutive_is_module"] += 1
                                tasks.append(dump_task)
                                dump_task = self._create_dump_task(pid, segment, current_modules)
                            elif pe_tools.checkMzHeaderInDump(segment_start):
                                self.dump_task_cases["consecutive_is_pe"] += 1
                                tasks.append(dump_task)
                                dump_task = self._create_dump_task(pid, segment, current_modules)
                            # if discarding of segments is enabled and
                            # - segment is reserved, not commited
                            # - segment is to large
                            elif (self.discard_reserved_segment_size is not None) and segment[5] == 0x2000 and segment[4] > self.discard_reserved_segment_size:
                                self.dump_task_cases["consecutive_is_large_reserved"] += 1
                                tasks.append(dump_task)
                                # Throw reserved region away
                                dump_task = None 
                            else:
                                self.dump_task_cases["consecutive_other"] += 1
                                dump_task.add_segment(segment)
                        else:
                            self.dump_task_cases["non_consecutive"] += 1
                            tasks.append(dump_task)
                            dump_task = self._create_dump_task(pid, segment, current_modules)
                    if index + 1 == len(sorted_segments):
                        self.dump_task_cases["last_segment"] += 1
                        tasks.append(dump_task)
            elif len(sorted_segments) == 1:
                self.dump_task_cases["single_segment"] += 1
                dump_task = DumpTask(pid, sorted_segments[0])
                tasks.append(dump_task)
        return tasks

    def _dump(self, tasks):
        dumps = []
        for task in tasks:
            process_handle = open_process(task.pid)
            segments = []
            for segment in task.segments:
                dump_memory = b64encode(b"\x00" * segment.size).decode("utf-8")
                dumped_size = segment.size
                if not segment.is_dummy:
                    dump_memory = read_memory(process_handle, segment.base_addr, segment.size)
                    dumped_size = len(dump_memory)
                    dump_memory = b64encode(dump_memory).decode("utf-8")
                segments.append({
                    "dump": dump_memory,
                    "base": segment.base_addr,
                    "size": segment.size,
                    "dumped_size": dumped_size,
                    "flags": segment.flags,
                    "isdummy": segment.is_dummy,
                })
            if task.segments:
                dumps.append({
                    "segments": segments,
                    "base": task.segments[0].base_addr,
                    "pid": task.pid,
                    "process_name": b64encode(name_of_process(process_handle)).decode("utf-8")
                })
        return dumps

    def collect_stats(self):
        return self.stats
