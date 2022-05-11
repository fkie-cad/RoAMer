import logging


class MappedMemoryFilter:

    def __init__(self, parent):
        self.parent = parent

    def update(self):
        pass

    def filter(self, tasks):
        filtered = []
        filtered_memory_size = 0
        all_memory_size = 0
        for task in tasks:
            filtered_segments = []
            for segment in task.segments:
                if segment.type & 0x40000:
                    filtered_memory_size += segment.size
                else:
                    filtered_segments.append(segment)
                all_memory_size += segment.size
            task.segments = filtered_segments
            filtered.append(task)
        logging.info("removed %d/%d bytes from dump tasks by removing mapped memory.", filtered_memory_size, all_memory_size)
        return filtered
