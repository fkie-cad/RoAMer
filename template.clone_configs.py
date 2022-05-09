# For each additional VM you want to use for parallel unpacking with the queue, 
# add a small partial config file below.
PARTIAL_CLONE_CONFIGS = [
    #### Example 1 ####
    # This example adds one additional VM instances:
    # {
    #     "host_port": 10001,
    #     "guest_ip": "192.168.56.102",
    #     "VM_CONTROLLER": "VboxManageController",
    #     "VM_NAME": "vm_name_Clone_1",
    #     "SNAPSHOT_NAME": "snapshot_name",
    # },

    #### Example 2 ####
    # This example adds three additional VM instances automatically:
    # {
    #     "host_port": 10000+i,
    #     "guest_ip": f"192.168.56.{101+i}",
    #     "VM_CONTROLLER": "VboxManageController",
    #     "VM_NAME": f"vm_name_Clone_{i}",
    #     "SNAPSHOT_NAME": "snapshot_name",
    # } for i in range(1,4)

]
