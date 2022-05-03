import logging
import os

class OwnPidFilter:

    def __init__(self, parent):
        self.parent = parent

    def update(self):
        pass

    def filter(self, tasks):
        filtered_tasks = []
        own_pid = os.getpid()
        for task in tasks:
            if task.pid != own_pid:
                filtered_tasks.append(task)
        logging.info("removed %d/%d dump tasks by excluding unpacker pid.", len(tasks) - len(filtered_tasks), len(tasks))
        return filtered_tasks

