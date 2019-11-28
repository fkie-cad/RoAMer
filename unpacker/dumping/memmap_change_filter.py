import logging


class MemMapChangeFilter:

    def __init__(self, parent):
        self.parent = parent

    def update(self):
        pass

    def filter(self, tasks):
        filtered = []
        for task in tasks:
            pid = task.get_pid()
            if not pid in self.parent.mem_map_changes:
                continue
            if not task.get_base_address() in self.parent.mem_map_changes[pid]:
                continue
            filtered.append(task)
        logging.info("removed %d/%d dump tasks by reducing to mem map changes only.", len(tasks) - len(filtered), len(tasks))
        return filtered
