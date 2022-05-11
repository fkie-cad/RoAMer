import argparse
from copy import deepcopy
import uuid
import psutil
import importlib
import json
import logging
import os
from threading import Thread
import time
import traceback
from multiprocessing import Process, Queue
from multiprocessing.connection import Client, Listener

from roamer.RoAMer import RoAMer

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")
FORMATER = logging.Formatter("%(asctime)-15s %(message)s")

#https://stackoverflow.com/questions/22235426/python-multiprocessing-worker-queue


##### Settings #####
WORKER_BASE_CONFIG = "config"
CLONE_PARTIAL_CONFIGS = "clone_configs"

LOCKFILE_NAME = "queue.lock"
LOCKFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCKFILE_NAME)


##### Shared #####
def get_current_server_lock_data():
    #FIXME: Not atomic
    if os.path.exists(LOCKFILE_PATH):
        with open(LOCKFILE_PATH, "r") as f:
            server_data = json.load(f)
        pid = server_data["pid"]
        if not psutil.pid_exists(pid):
            return
        return server_data
    





##### Server #####
class IdLoggingStream:
    def __init__(self, id, send_method):
        self.id = id
        self.send_method = send_method

    def write(self, record):
        self.send_method(
            {
                "id": self.id,
                "logging": True,
                "record": record,
            }
        )

    def close(self):
        pass


def worker(work_queue, done_queue, partial_config):
    print("worker up", str(partial_config))
    for task in iter(work_queue.get, 'STOP'):
        try:
            print(task)
            logging_handler = logging.StreamHandler(IdLoggingStream(task["id"], done_queue.put))
            logging_handler.terminator = ""
            logging_handler.setFormatter(FORMATER)
            run_task(task, partial_config, logging_handler)
            done_queue.put(
                {
                    "state": "finished",
                    "id": task["id"],
                }
            )
        except Exception as e:        
            done_queue.put(
                {
                    "state": "failed",
                    "id": task["id"],
                    "error": traceback.format_exc(),
                }
            )


def run_task(task, partial_config, logging_handler):

    #loggers = ["roamer.VmController", "roamer", "roamer.RoAMer", "roamer.CuckooVirtualBox"]
    loggers = ["roamer"]
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.addHandler(logging_handler)

    loaded_base_config = importlib.import_module(task["config"])
    config = appy_partial_on_base_config(loaded_base_config, partial_config)
    roamer = RoAMer(config, task["headless"], task["vm"], task["snapshot"], task["ident"])
    roamer.run(task["sample"], output_folder=task["output_folder"])

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.removeHandler(logging_handler)

class FakeConfig:
    def __init__(self, input_config):
        for key in input_config.__dict__.keys():
            if not key.startswith("__") and key.isupper():
                setattr(self, key, deepcopy(getattr(input_config, key)))

def partial_from_base_config(base_config):
    partial = {}
    partial["VM_CONTROLLER"] = base_config.VM_CONTROLLER 
    partial["VM_NAME"] = base_config.VM_NAME
    partial["SNAPSHOT_NAME"] = base_config.SNAPSHOT_NAME
    partial["host_port"] = base_config.UNPACKER_CONFIG["host_port"]
    partial["guest_ip"] = base_config.UNPACKER_CONFIG["guest_ip"]
    return partial

def appy_partial_on_base_config(base, partial):
    new_config = FakeConfig(base)
    new_config.VM_CONTROLLER = partial["VM_CONTROLLER"]
    new_config.VM_NAME = partial["VM_NAME"]
    new_config.SNAPSHOT_NAME = partial["SNAPSHOT_NAME"]
    new_config.UNPACKER_CONFIG["host_port"] = partial["host_port"]
    new_config.UNPACKER_CONFIG["guest_ip"] = partial["guest_ip"]
    return new_config

class Server:
    def __init__(self):
        try:
            self.get_listener_and_lock()
            self.start_worker()

            #Network: 
            self.clients = [] 
            Thread(target=self.handle_messages_from_workers).start()
            #Thread(target=self.handle_incomming_connections).start()
            self.handle_incomming_connections() # this will block
        finally:
            unlock_server()

    def get_partial_configs(self):
        base = importlib.import_module(WORKER_BASE_CONFIG)
        partials = importlib.import_module(CLONE_PARTIAL_CONFIGS)
        return partials.PARTIAL_CLONE_CONFIGS+[partial_from_base_config(base)]

    def start_worker(self):
        # Start Worker
        self.work_queue = Queue()
        self.done_queue = Queue()
        processes = []
        for partial_config in self.get_partial_configs():
            p = Process(target=worker, args=(self.work_queue, self.done_queue, partial_config))
            p.start()
            processes.append(p)
            #work_queue.put('STOP')
        # for p in processes:
        #     p.join()    
        #     done_queue.put('STOP')
        # for status in iter(done_queue.get, 'STOP'): 
    

    def get_listener_and_lock(self):
        with open(LOCKFILE_PATH, "w") as f:
            self.listener = Listener() 
            print(self.listener.address)
            server_data = {
                "address": self.listener.address,
                "pid": os.getpid(),
            }
            json.dump(server_data, f)

    def handle_messages(self, connection):
        for message in iter(connection.recv, "CLOSE"):
            self.work_queue.put(message)
    
    def handle_messages_from_workers(self):
        for message in iter(self.done_queue.get, "STOP"):
            for client in self.clients:
                try:
                    client.send(message)
                except Exception as e:
                    self.clients.remove(client)

    def handle_incomming_connections(self):
        while True:
            connection = self.listener.accept()
            self.clients.append(connection)
            Thread(target=self.handle_messages, args=(connection,)).start()


def unlock_server():
    os.remove(LOCKFILE_PATH)


def start_server_safe():
    server_data = get_current_server_lock_data()
    if not server_data:
        #Process(target=Server).start()
        #Thread(target=Server).start()
        Server() # blocks
        time.sleep(0.1)
    else:
        LOG.warning("Server is already running. Did not start a new server.")
    server_data = get_current_server_lock_data()
    if server_data is None:
        raise RuntimeError("Could not start roamerqueue server")
    return server_data



##### Client #####

def connect_to_server(server_data):
    return Client(server_data["address"])


def get_files(target_path):
    samples = []
    try:
        if os.path.isdir(target_path):
            for filename in os.listdir(target_path):
                sample = os.path.join(target_path, filename)
                if os.path.isfile(sample):
                    samples.append(os.path.abspath(sample))
        elif os.path.isfile(target_path):
            samples.append(os.path.abspath(target_path))
        else:
            LOG.error("Target was neither file nor directory, aborting.")
    except Exception:
        LOG.exception("uncaught exception")
    return samples

def unpack_samples(samples, config, headless, ident, output_folder, block):
    server_data = get_current_server_lock_data()
    if not server_data:
        raise ValueError("Server not available")
    connection = connect_to_server(server_data)

    assert connection

    if output_folder is not None:
        output_folder = os.path.abspath(output_folder)

    task_base = {
        "sample": None,
        "config": config,
        "headless": headless,
        "vm": "",
        "snapshot": "",
        "id": None,
        "output_folder": output_folder,
        "ident": ident,
    }
    samples = get_files(samples)
    ids = []
    for sample in samples:
        task = dict(**task_base)
        task["sample"] = sample
        id = uuid.uuid4()
        task["id"] = id
        ids.append(id)
        connection.send(task)

    if block and ids:
        for message in iter(connection.recv, "STOP"):
            if message["id"] in ids:
                if "logging" in message and message["logging"]:
                    print(message["record"], flush=True)
                else:
                    print(message, flush=True)
                    ids.remove(message["id"])
            if not ids:
                break
    
    connection.send("CLOSE")
    time.sleep(0.1)        


##### CLI #####

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RoAMer')
    subparsers = parser.add_subparsers(dest="action", required=True)
    send_parser = subparsers.add_parser("unpack")
    send_parser.add_argument('Samples', metavar='Sample', type=str, help='Path to sample or folder of samples')
    send_parser.add_argument('--config', action='store', help="Which config shall be used?", default=WORKER_BASE_CONFIG)
    send_parser.add_argument('--no-headless', action='store_false', help='Start the Sandbox in headless mode', dest="headless")
    send_parser.add_argument('--ident', action="store", help="Configure an identifier for the output.", default="")
    send_parser.add_argument('--output', action="store", help="Specify a custom output folder for the dumps", default=None)
    send_parser.add_argument('--block', action="store_true")
    server_parser = subparsers.add_parser("server")

    args = parser.parse_args()

    print(args.action)
    if args.action == "server":
        start_server_safe()
    elif args.action == "unpack":
        unpack_samples(args.Samples, args.config, args.headless, args.ident, args.output, args.block)

