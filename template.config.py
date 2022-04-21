import os

# RoAMer related
THIS_FILE_PATH = str(os.path.abspath(__file__))
PROJECT_ROOT = str(os.path.abspath(os.sep.join([THIS_FILE_PATH, ".."])))
BIN_ROOT = str(os.path.abspath(os.sep.join([PROJECT_ROOT, "roamer", "bin"])))
UNPACKER_CONFIG = {
    "host_ip": '192.168.56.1',
    "host_port": 10000,
    "guest_ip": "1.1.1.1",
    "guest_port": 10000,
    "debug_sleep": 0,
    "socket_timeout": 480,

    "parameters": [
        {
            "name": "4x5_hook_spoofuser",
            "hook32": "TP_EM0_sleep.dll",
            "hook64": 0,
            "monitoring_intervals": 4,
            "monitoring_interval_length": 5,
            "monitoring_switches": [
                "processes"
            ],
            # Have the unpacker reduce the candidate list of segments to dump based on 
            # these filters.
            "dump_filters": [
                "pe_header_whitelist",
                "memmap_change",
                "only_executable_filter",
                "mapped_memory"
            ],
            # Control over merging of gapped segments
            # set to 0x1000 to enable correct merging of .NET memory dumps
            # set to 0x10000 to avoid merging unrelated heap buffers
            # set to None to disable discarding of any reserved segments
            "discard_reserved_segment_size": 0x10000, 
            "additional_pe_whitelist": {
                "EP_EM0_sleep.dll": ["52d6854748d2b08c18392b27e705c980e1b7c3b52eb433393ba78eb001a6c42f"],
                "both_EM0_sleep.dll": ["7b3315fd53a972a7a76312de2a6e1a89bb4e0c5329b0932e3de0a0f95eb66bdd"],
                "TP_EM0_sleep.dll": ["a4a7ea713f350193c136e5c00067fd095584417af1f353e46dfc7c9439e0305c"],
                "dotNet1.dll": ["c4aa77a6556cc19a1f1e5f5dd85ef7966489d413c19ea7433d9a4e244ddb4450"],
                "dotNet2.dll": ["0bf521a45ff4ad7bb21220a069441a60d48874a61e30659bbb6a65f2d616d2fd"],
                "dotNet3.dll": ["5bb85f402bed10719d8fcf5151c7ac9e989ee6b6fed3232283a126dcb79fb633"],
                "dotNet4.dll": ["d3142c2dc9659e1ddd08efc42a084681ca1d8d33f51ee0a878a63ebf1d521ba2"],
                "dotNet5.dll": ["88d0b9411fe74c3d757495ac8f87a2542acf4bd7c1f723593f73c3c3bbe6381d"],
                "dotNet6.dll": ["7dac91e7e5a81dff093eb95fda1a022e2492476551e6ff33196dce1c9628cea9"],
                "dotNet7.dll": ["2e0a4960905e2f0d1956691ff31e7a75a4f06db0b0a989821fd52fb8d89ac5f5"],
                "dotNet8.dll": ["b371143568c9744f395400acaff6b73149d18906d8fce74d7a48d2f9cceb9989"]
            },
            # if "spoof_user" is True and after "sample_start_delay" seconds, 
            # perform a double click at "desktop_sample_pos_x/y" to start the sample
            "sample_start_delay": 5,
            "spoof_user": 1,
            "desktop_sample_pos_x": 40,
            "desktop_sample_pos_y": 40
        }   
    ]
}

# Virtualization related
## VM_CONTROLLER: choose "VboxManageController" for VirtualBox or "KvmManageController" for KVM
VM_CONTROLLER = "VboxManageController"
VM_NAME = "vm_name"
SNAPSHOT_NAME = "snapshot_name"
