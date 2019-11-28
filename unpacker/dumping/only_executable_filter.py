import logging


class OnlyExecutableFilter:

    def __init__(self, parent):
        self.parent = parent

    def update(self):
        pass

    def filter(self, tasks):
        filtered_tasks = []
        execution_flags = [0x40, 0x10, 0x20, 0x80]
        for task in tasks:
            for segment in task.segments:
                if segment.flags in execution_flags:
                    filtered_tasks.append(task)
                    break
        logging.info("removed %d/%d dump tasks by removing non-executable tasks.", len(tasks) - len(filtered_tasks), len(tasks))
        return filtered_tasks
