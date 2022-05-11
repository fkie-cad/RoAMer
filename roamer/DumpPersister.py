import json
import os
import datetime
import base64
from copy import deepcopy

from utility.pe_tools import iterate_pe_headers


class DumpPersister:
    def __init__(self, prefix, returned_data, config):
        self._folder_name = prefix + "_dumps_" + datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        self._returned_data = returned_data
        self.config = config
        self._persist_data()

    def _persist_data(self):
        os.makedirs(self._folder_name)
        self._persist_log()
        for config_name in self._returned_data.keys():
            self._persist_config_result(config_name)

    def _persist_log(self):
        path = os.path.join(self._folder_name, "log.txt")
        with open(path, "w") as f_out:
            f_out.write(self._returned_data["log"])
        self._returned_data.pop("log")

    def _persist_config_result(self, config_name):
        result_path = self._folder_name + os.sep + config_name
        os.makedirs(result_path)
        _persist_as_json(self._returned_data[config_name]["stats"], os.path.join(result_path, "vm_stats.json"))
        _persist_as_json(self._returned_data[config_name]["observations"],
                         os.path.join(result_path, "observations.json"))
        _persist_dumps(self._returned_data[config_name], result_path, self.config)


def _strip_trailing_zeroes(data):
    data = data.rstrip(b"\x00")
    num_missing_bytes = 0x1000 - (len(data) % 0x1000)
    data += b"\x00" * (0x1000 + num_missing_bytes)
    return data


def _persist_dump(dump, result_path, config):
    merged_segments = _merge_dump_segments(dump)
    offsets = set()
    offsets.add(0)
    # Always dump original file
    # Add offsets of all contained PE files
    for offset, _ in iterate_pe_headers(merged_segments):
        offsets.add(offset)
    for offset in offsets:
        dump_name = "%d_0x%08x" % (dump["pid"], dump["base"]+offset)
        dump_path = os.path.join(result_path, dump_name)
        with open(dump_path, "wb") as fPE:
            fPE.write(_strip_trailing_zeroes(merged_segments[offset:]))
    dump_name = "%d_0x%08x" % (dump["pid"], dump["base"])
    dump_info = deepcopy(dump)
    dump_info["dump_name"] = dump_name
    segment_infos = []
    for segment in dump_info["segments"]:
        segment.pop("dump")
        segment["base"] = "0x%x" % segment["base"]
        segment["flags"] = _get_protection_flags(segment["flags"])
        segment_infos.append(segment)
    dump_info["segments"] = segment_infos
    return dump_info


def _decode_process_name(b64_process_name, human_readable_config):
    if human_readable_config == "if_ascii":
        decoded_bytes = base64.b64decode(b64_process_name)
        if decoded_bytes.isascii():
            process_name = decoded_bytes.decode("ascii")
        else:
            process_name = b64_process_name
    elif human_readable_config == "escape":
        process_name = str(base64.b64decode(b64_process_name))
    else: # especially if it is set to "never"
        process_name = b64_process_name
    return process_name

def _persist_dumps(config_result, result_path, config):
    dump_stats = {}
    for dump in config_result["dumps"]:
        dump_info = _persist_dump(dump, result_path, config)
        dump_stats[dump_info["dump_name"]] = dump_info
        dump_info["process_name"] = _decode_process_name(dump_info["process_name"], config["human_readable_process_names"])
    _persist_as_json(dump_stats, os.path.join(result_path, "dump_stats.json"))


def _persist_as_json(data, result_path):
    with open(result_path, "w") as f_out:
        f_out.write(json.dumps(data, indent=1, sort_keys=True))


def _merge_dump_segments(dump):
    result = b""
    for segment in dump["segments"]:
        if segment["isdummy"]:
            result += b"\x00" * segment["size"]
        else:
            result += base64.b64decode(segment["dump"]) + b"\x00" * (segment["size"] - segment["dumped_size"])
    return result


def _get_protection_flags(flags):
    protection = ""
    modifier = ""
    if flags & 0x1:
        protection = "NOACCESS"
    elif flags & 0x2:
        protection = "R"
    elif flags & 0x4:
        protection = "RW"
    elif flags & 0x8:
        protection = "W Copy"
    elif flags & 0x10:
        protection = "X"
    elif flags & 0x20:
        protection = "RX"
    elif flags & 0x40:
        protection = "RWX"
    elif flags & 0x20:
        protection = "RWX Copy"
    if flags & 0x1:
        modifier = "GUARD"
    elif flags & 0x2:
        modifier = "NOCACHE"
    elif flags & 0x4:
        modifier = "WRITECOMBINE"
    return (protection + " " + modifier).strip()


def persist_data(sample_path, returned_data, ident, config):
    prefix = sample_path + "_" + ident if ident else sample_path
    DumpPersister(prefix, returned_data, config)
