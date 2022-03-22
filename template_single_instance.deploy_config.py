import os

# RoAMer related
THIS_FILE_PATH = str(os.path.abspath(__file__))
PROJECT_ROOT = str(os.path.abspath(os.sep.join([THIS_FILE_PATH, ".."])))
BIN_ROOT = str(os.path.abspath(os.sep.join([PROJECT_ROOT, "roamer", "bin"])))

BUILD_INSTANCE = {
    "client_paths": {
        "receiver": "{USERPATH}Desktop\\roamer.exe", # used for update_receiver
        "repo": "{USERPATH}roamer_repo", #used for compiling source / storing binaries
        "repo_zip": "{USERPATH}roamer.zip", #used for compiling source
        "to_whitelist": "C:\\", #used to create whitelist
    },

    "host_ip": '192.168.56.1',
    "host_port": 10000,
    "guest_ip": "1.1.1.1",
    "guest_port": 10000,
    "debug_sleep": 0,
    "socket_timeout": 480,

    "staged_update": True,    # requires python on client, SHOULD BE DISABLED FOR PROD
    "requires_cleaning_before_snapshot": False,

    # Virtualization related
    # VM_CONTROLLER choose "VboxManageController" for VirtualBox or "KvmManageController" for KVM
    "VM_CONTROLLER": "VboxManageController",
    "VM_NAME": "vm_name",
    "SNAPSHOT_NAME": "snapshot_name",
}

PROD_INSTANCE = BUILD_INSTANCE



                     
TASKS = [
    "unpacker",
    #"receiver",    # Not implemented yet
    #"whitelister", # Not implemented yet
    #"whitelist",   # Not implemented yet
    #"bootstrap"    # Not implemented yet
]

