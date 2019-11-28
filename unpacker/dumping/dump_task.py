from unpacker.winwrapper.utilities import open_process, name_of_process


class SegmentInfo:

    def __init__(self, raw_segment, is_dummy=False):
        self.base_addr = raw_segment[0]
        self.size = raw_segment[4]
        self.flags = raw_segment[6]
        self.type = raw_segment[7]
        self.is_dummy = is_dummy

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other) 


class DumpTask:

    def __init__(self, pid, first_segment):
        self.pid = pid
        self.process_name = name_of_process(open_process(self.pid))
        self.segments = []
        self.add_segment(first_segment)
        self.module = None

    def set_module(self, module):
        self.module = module

    def is_in_own_module_range(self, query_addr):
        if not self.module:
            return False
        return (query_addr >= self.module[0]) and (query_addr < self.module[0] + self.module[1])

    def add_segment(self, segment):
        # baseAddr, size, flags, isDummy
        segment_info = SegmentInfo(segment)
        if segment_info not in self.segments:
            self.segments.append(segment_info)

    def add_dummy_segment(self, dummy_address, dummy_size):
        dummy_segment = SegmentInfo((dummy_address, 0, 0, 0, dummy_size, 0, 0, 0), is_dummy=True)
        if dummy_segment not in self.segments:
            self.segments.append(dummy_segment)

    def get_current_top_address(self):
        return self.segments[-1].base_addr + self.segments[-1].size

    def get_num_segments(self):
        return len(self.segments)

    def get_total_memory_size(self):
        return sum([seg.size for seg in self.segments])

    def get_pid(self):
        return self.pid

    def get_base_address(self):
        return self.segments[0].base_addr

    def __str__(self):
        if self.segments:
            return "PID %d (%s), @0x%x, 0x%x bytes" % (self.pid, self.process_name, self.segments[0].base_addr, sum([seg.size for seg in self.segments]))
        else:
            return "PID %d (%s), EMPTY" % (self.pid, self.process_name)
