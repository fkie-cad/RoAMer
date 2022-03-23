import argparse

from roamer.RoAMerDeployer import ExecuteDeployerTasks
import importlib






if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RoAMerDeployer')
    parser.add_argument('Tasks', metavar='Task', type=str, nargs="*", help='Path to sample or folder of samples')
    parser.add_argument('--no-headless', action='store_false', help='Start the Sandbox in headless mode', dest="headless")
    parser.add_argument('--vm', action='store', help='This can be used to force a VM past the config-file', default="")
    parser.add_argument('--snapshot', action='store', help='This can be used to force a snapshot past the config-file', default="")
    parser.add_argument('--config', action='store', help="Which config shall be used?", default="deploy_config")
    parser.add_argument('--ident', action="store", help="Configure an identifier for the output.", default="")

    args = parser.parse_args()
    deployer = ExecuteDeployerTasks(importlib.import_module(args.config), args.Tasks, args.headless, args.vm, args.snapshot, args.ident)
