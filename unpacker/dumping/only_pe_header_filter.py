import logging

from utility.pe_tools import checkMzHeaderInDump
from unpacker.winwrapper.utilities import open_process, read_memory

class OnlyPeHeaderFilter:

    def __init__(self, parent):
        self.parent = parent

    def update(self):
        pass
    
    def _task_contains_pe_header(self, task):
        process_handle = open_process(task.pid)
        for segment in task.segments:
            if not segment.is_dummy:
                data = read_memory(process_handle, segment.base_addr, segment.size)
                if checkMzHeaderInDump(data):
                    return True
        return False

    def filter(self, tasks):
        filtered_tasks = []
        for task in tasks:
            if self._task_contains_pe_header(task):
                filtered_tasks.append(task)

        logging.info("removed %d/%d dump tasks by removing tasks which do not contain a PE header.", len(tasks) - len(filtered_tasks), len(tasks))
        return filtered_tasks


