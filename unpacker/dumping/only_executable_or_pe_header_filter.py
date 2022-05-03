import logging

from utility.pe_tools import checkMzHeaderInDump
from unpacker.winwrapper.utilities import open_process, read_memory

class OnlyExecutableOrPeHeaderFilter:

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
        execution_flags = [0x40, 0x10, 0x20, 0x80]
        for task in tasks:
            for segment in task.segments:
                if segment.flags in execution_flags:
                    filtered_tasks.append(task)
                    break
            else:
                if self._task_contains_pe_header(task):
                    filtered_tasks.append(task)

        logging.info("removed %d/%d dump tasks by removing non-executable tasks which do not contain a PE header.", len(tasks) - len(filtered_tasks), len(tasks))
        return filtered_tasks
