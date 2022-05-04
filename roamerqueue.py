import argparse
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


def worker(work_queue, done_queue, config):
    for task in iter(work_queue.get, 'STOP'):
        try:
            print(task)
            logging_handler = logging.StreamHandler(IdLoggingStream(task["id"], done_queue.put))
            logging_handler.terminator = ""
            logging_handler.setFormatter(FORMATER)
            run_task(task, config, logging_handler)
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


def run_task(task, config, logging_handler):

    #loggers = ["roamer.VmController", "roamer", "roamer.RoAMer", "roamer.CuckooVirtualBox"]
    loggers = ["roamer"]
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.addHandler(logging_handler)

    roamer = RoAMer(config, task["headless"], task["vm"], task["snapshot"], task["ident"])
    roamer.run(task["sample"])

    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.removeHandler(logging_handler)



worker_configs = ["config", "config_clone1"]




#FIXME: use global location
LOCKFILE_NAME = "queue.lock"
LOCKFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCKFILE_NAME)

class Server:
    def __init__(self):
        self.get_listener_and_lock()
        self.clients = [] 
        self.start_worker()
        Thread(target=self.handle_messages_from_workers).start()
        #Thread(target=self.handle_incomming_connections).start()
        self.handle_incomming_connections() # this will block

    def start_worker(self):
        # Start Worker
        self.work_queue = Queue()
        self.done_queue = Queue()
        processes = []
        for config in worker_configs:
            loaded_config = importlib.import_module(config)
            p = Process(target=worker, args=(self.work_queue, self.done_queue, loaded_config))
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

    def unlock(self):
        os.remove(LOCKFILE_PATH)

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


def get_current_server_lock_data():
    #FIXME: Not atomic
    if os.path.exists(LOCKFILE_PATH):
        with open(LOCKFILE_PATH, "r") as f:
            server_data = json.load(f)
        pid = server_data["pid"]
        if not psutil.pid_exists(pid):
            return
        return server_data
    


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


def start_server_safe():
    server_data = get_current_server_lock_data()
    if not server_data:
        #Process(target=Server).start()
        Thread(target=Server).start()
        time.sleep(0.1)
        # Server()
    server_data = get_current_server_lock_data()
    if server_data is None:
        raise RuntimeError("Could not start roamerqueue server")
    return server_data

def connect_to_server(server_data):
    return Client(server_data["address"])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RoAMer')
    parser.add_argument('Samples', metavar='Sample', type=str, help='Path to sample or folder of samples')
    parser.add_argument('--no-headless', action='store_false', help='Start the Sandbox in headless mode', dest="headless")
    parser.add_argument('--vm', action='store', help='This can be used to force a VM past the config-file', default="")
    parser.add_argument('--snapshot', action='store', help='This can be used to force a snapshot past the config-file', default="")
    parser.add_argument('--config', action='store', help="Which config shall be used?", default="config")
    parser.add_argument('--ident', action="store", help="Configure an identifier for the output.", default="")
    parser.add_argument('--allow-start-server', action="store_true")
    parser.add_argument('--block', action="store_true")

    args = parser.parse_args()
    
    if args.allow_start_server:
        server_data = start_server_safe()
    else:
        server_data = get_current_server_lock_data()
        if not server_data:
            raise ValueError("Server not available")
    connection = connect_to_server(server_data)

    assert connection

    task_base = {
        "sample": None,
        "config": None,
        "headless": args.headless,
        "vm": "",
        "snapshot": "",
        "id": None,
        "ident": args.ident,
    }
    samples = get_files(args.Samples)
    ids = []
    for sample in samples:
        task = dict(**task_base)
        task["sample"] = sample
        id = uuid.uuid4()
        task["id"] = id
        ids.append(id)
        connection.send(task)

    if args.block and ids:
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



