import argparse
from copy import deepcopy
from queue import Empty
import queue
import uuid
import psutil
import importlib
import json
import logging
import os
from threading import Thread
import time
import traceback
from multiprocessing import Process, JoinableQueue
from multiprocessing.connection import Client, Listener
from queue import Queue

from roamer.RoAMer import RoAMer
from roamer.VmController import VmController

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")
FORMATER = logging.Formatter("%(asctime)-15s %(message)s")


##### Settings #####
WORKER_BASE_CONFIG = "config"
CLONE_PARTIAL_CONFIGS = "clone_configs"

LOCKFILE_NAME = "queue.lock"
LOCKFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCKFILE_NAME)



##### ExtendedQueue #####

class ExtendedQueue(Queue):
    def remove(self, element):
        with self.not_empty:
            self.queue.remove(element)
            self.not_full.notify()

    def __iter__(self):
        return self.queue.__iter__()


##### Shared #####
def get_current_server_lock_data():
    #FIXME: Not atomic
    if os.path.exists(LOCKFILE_PATH):
        with open(LOCKFILE_PATH, "r") as f:
            server_data = json.load(f)
        pid = server_data["pid"]
        if not psutil.pid_exists(pid):
            return None
        return server_data

def iter_connection(connection):
    try:
        while True:
            yield connection.recv()
    except EOFError:
        return


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

def stop_vm(partial_config):
    vm_controller = VmController.factory(partial_config["VM_CONTROLLER"], True)
    vm_controller.stop_vm(partial_config["VM_NAME"])

def worker(work_queue, done_queue, partial_config):
    print("worker up", str(partial_config))
    for task in iter(work_queue.get, 'STOPWORKER'):
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
        work_queue.task_done()


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


class WorkerHandler:

    def __init__(self, on_message):
        self.onMessage = on_message
        self.partial_configs = self._get_partial_configs()
        self.workers = {}
        self.worker_queues = {}


    def _get_partial_configs(self):
        base = importlib.import_module(WORKER_BASE_CONFIG)
        partials = importlib.import_module(CLONE_PARTIAL_CONFIGS)
        return partials.PARTIAL_CLONE_CONFIGS+[partial_from_base_config(base)]

    def stop_all_vms(self):
        for partial_config in self.partial_configs:
            try:
                stop_vm(partial_config)
            except Exception:
                pass
        time.sleep(2)
        for partial_config in self.partial_configs:
            try:
                stop_vm(partial_config)
            except Exception:
                pass
    
    def run_feed_workers(self, worker_queue):
        while True:
            worker_queue.join()
            task = self.work_queue.get()
            worker_queue.put(task)
            if task == "STOPWORKER":
                break


    def start_workers(self):
        # Start Worker
        self.work_queue = ExtendedQueue()
        self.done_queue = JoinableQueue()
        for i, partial_config in enumerate(self.partial_configs):
            queue = JoinableQueue()
            p = Process(target=worker, args=(queue, self.done_queue, partial_config))
            p.start()
            self.workers[i] = p
            self.worker_queues[i] = queue
            Thread(target=self.run_feed_workers, args=(queue,)).start()
            #work_queue.put('STOP')
        # for p in processes:
        #     p.join()    
        #     done_queue.put('STOP')
        # for status in iter(done_queue.get, 'STOP'): 

    def enqueue_job(self, job):
        self.work_queue.put(job)

    def cancel_jobs(self, job_ids):
        remove_list = []
        for job in self.work_queue:
            if job and "id" in job and job["id"] in job_ids:
                remove_list.append(job)
        for job_to_cancel in remove_list:
            try:
                self.work_queue.remove(job_to_cancel)
                self.done_queue.put(
                    {
                        "state": "cancelled",
                        "id": job_to_cancel["id"],
                    }
                )
            except ValueError:
                print(f"job {job_to_cancel} vanished while trying to remove it")
                pass
        removed_ids = set()
        for job in remove_list:
            removed_ids.add(job["id"])
        for id in job_ids:
            if id not in removed_ids:
                print(f"Could not remove job {id}")



    def clear_queue(self):
        try:
            while True:
                task = self.work_queue.get_nowait()
                if task and "id" in task:
                    self.done_queue.put(
                        {
                            "state": "cleared",
                            "id": task["id"],
                        }
                    )
        except Empty:
            pass 

    def run_handle_messages(self):
        for message in iter(self.done_queue.get, "STOP"):
            self.onMessage(message, None)

    def stop_receiving_worker_messages(self):
        self.done_queue.put("STOP")

    def wait_for_workers(self):
        for process in self.workers.values():
            process.join()
    
    def kill_workers(self):
        # This allows feeders to shut down
        for worker_queue in self.worker_queues.values():
            try:
                worker_queue.task_done()
            except ValueError:
                pass
        for process in self.workers.values():
            process.terminate()

    def send_stop_signal(self):
        for _ in range(len(self.workers)):
            self.work_queue.put("STOPWORKER")
    
    def shutdown(self, force=False):
        logging.info("enqueue signal for worker to stop")
        self.send_stop_signal()
        if force:
            logging.info("terminate workers")
            self.kill_workers()
            logging.info("shutdown vms")
            self.stop_all_vms()
        else:
            logging.info("wait for workers to terminate, this might take a while")
            self.wait_for_workers()
        logging.info("stop listening for workers")
        self.stop_receiving_worker_messages()

class ClientHandler:

    def __init__(self, listener: Listener, on_message):
        self.clients = {}
        self.listener = listener
        self.onMessage = on_message

    def send_message_to_client(self, message, client_id):
        try:
            self.clients[client_id].send(message)
        except Exception as e:
            self.clients.pop(client_id, None)

    def send_message_to_clients(self, message):
        for client_id in [*self.clients.keys()]:
            self.send_message_to_client(message, client_id)

    def handle_messages(self, connection, client_id, message_backlog):
        for message in message_backlog:
            self.onMessage(message, client_id)
        for message in iter_connection(connection):
            self.onMessage(message, client_id)
    
    def run(self):
        while True:
            connection = self.listener.accept()
            client_id = uuid.uuid4()
            self.clients[client_id] = connection
            message_backlog = []
            if connection.poll(0.1):
                try:
                    first_message = connection.recv()
                except EOFError:
                    continue
                if first_message == "STOPLISTENER":
                    connection.close()
                    break
                else:
                    message_backlog.append(first_message)
            Thread(target=self.handle_messages, args=(connection,client_id,message_backlog)).start()

    def _stop_listening(self):
        connection = Client(self.listener.address)
        connection.send("STOPLISTENER")

    def kill_connection(self, client_id):
        self.send_message_to_client("STOPCLIENT", client_id)
        connection = self.clients.pop(client_id, None)
        if connection:
            try:
                if not connection.closed: 
                    connection.close()
            except Exception:
                print(f"could not shutdown client {client_id}:\n{traceback.format_exc()}")
                pass
    
    def _kill_running_connections(self):
        for client_id in [*self.clients.keys()]:
            self.kill_connection(client_id)
    
    def shutdown(self):
        logging.info("stop accepting new clients")
        self._stop_listening()
        logging.info("kill existing clients")
        self._kill_running_connections()
        logging.info("kill existing clients done")

class Server:
    def __init__(self):
        self.get_listener_and_lock() # sets self.listerner
        self.worker_handler = WorkerHandler(self.on_worker_message)
        self.client_handler = ClientHandler(self.listener, self.on_client_message)
        self.allow_queue = True
    
    def disallow_enqueueing(self):
        self.allow_queue = False

    def run(self):
        self.worker_handler.start_workers()
        Thread(target=self.worker_handler.run_handle_messages).start()
        self.client_handler.run() # this will block


    def get_listener_and_lock(self):
        with open(LOCKFILE_PATH, "w") as f:
            self.listener = Listener() 
            print(self.listener.address)
            server_data = {
                "address": self.listener.address,
                "pid": os.getpid(),
            }
            json.dump(server_data, f)

    def on_client_message(self, message, client_id):
        try:
            if message["task"] == "unpack":
                if self.allow_queue:
                    self.worker_handler.enqueue_job(message)
                else:
                    self.worker_handler.done_queue.put(
                        {
                            "state": "rejected",
                            "id": message["id"],
                        }
                    )
                    pass
            elif message["task"] == "clear-queue":
                self.worker_handler.clear_queue()
            elif message["task"] == "cancel":
                self.worker_handler.cancel_jobs(message["ids"])
            elif message["task"] == "shutdown":
                self.shutdown(force=message["force"], finish_queue=message["finish_queue"])
            else:
                logging.error("Error handling message from client: unknown task")
        except Exception:
            logging.error("Error handling message from client\n"+traceback.format_exc())

    def on_worker_message(self, message, worker_id):
        self.client_handler.send_message_to_clients(message)

    def panic_cleanup(self):
        unlock_server()
        self.worker_handler.stop_all_vms()

    def shutdown(self, force=False, finish_queue=False):
        logging.info("initiate shutdown sequence")
        logging.info("disallow enqueueing")
        self.disallow_enqueueing()
        if not finish_queue:
            logging.info("clear queue")
            self.worker_handler.clear_queue()
        self.worker_handler.shutdown(force=force)
        self.client_handler.shutdown()
        unlock_server()
        # NOTE: cleanup does not need to be called, as this is already done in finally

def unlock_server():
    if os.path.exists(LOCKFILE_PATH):
        os.remove(LOCKFILE_PATH)


def start_server_safe():
    server_data = get_current_server_lock_data()
    if not server_data:
        #Process(target=Server).start()
        #Thread(target=Server).start()
        try:
            server = Server()
            server.run() # blocks
        except KeyboardInterrupt:
            server.shutdown()
        except Exception:
            logging.error("run panic-cleanup because of uncaught exception:\n"+traceback.format_exc())
            server.panic_cleanup()
    else:
        LOG.warning("Server is already running. Did not start a new server.")



##### Client #####

def connect_to_server():
    server_data = get_current_server_lock_data()
    if not server_data:
        raise ValueError("Server not available")
    connection = Client(server_data["address"])

    assert connection
    return connection


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


def monitor_ids(connection, ids):
    ids = [uuid.UUID(id) if isinstance(id, str) else id for id in ids]
    for message in iter_connection(connection):
        if message == "STOPCLIENT":
            break
        if message["id"] in ids:
            if "logging" in message and message["logging"]:
                print(message["record"], flush=True)
            else:
                print(message, flush=True)
                if message["state"] not in ["started", "enqueued"]:
                    ids.remove(message["id"])
        if not ids:
            break
    if ids:
        logging.warning(f"Server closed connection but there are still jobs to monitor: {ids}")


def clear_queue(connection):
    connection.send(
        {
            "task":"clear-queue",
        }
    )

def cancel_ids(connection, ids):
    ids = [uuid.UUID(id) if isinstance(id, str) else id for id in ids]
    connection.send(
        {
            "task":"cancel",
            "ids": ids,
        }
    )

def shutdown_server(connection, force=False, finish_queue=False):
    connection.send(
        {
            "task":"shutdown",
            "force": force,
            "finish_queue": finish_queue,
        }
    )


def unpack_samples(samples, config, headless, ident, output_folder, block):
    with connect_to_server() as connection: # might throw
        if output_folder is not None:
            output_folder = os.path.abspath(output_folder)

        task_base = {
            "task": "unpack",
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
            print(id)
            ids.append(id)
            connection.send(task)

        if block and ids:
            monitor_ids(connection, ids)
    




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
    monitor_parser = subparsers.add_parser("monitor")
    monitor_parser.add_argument('job_ids', nargs="+", metavar='Job IDs', type=str, help='Ids of Jobs to monitor')
    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.add_argument('job_ids', nargs="+", metavar='Job IDs', type=str, help='Ids of Jobs to cancel')
    clear_parser = subparsers.add_parser("clear-queue")
    shutdown_parser = subparsers.add_parser("shutdown")
    shutdown_flag_group = shutdown_parser.add_mutually_exclusive_group()
    shutdown_flag_group.add_argument('--force', action="store_true")
    shutdown_flag_group.add_argument('--finish-queue', action="store_true")

    args = parser.parse_args()

    if args.action == "server":
        start_server_safe()
    elif args.action == "unpack":
        unpack_samples(args.Samples, args.config, args.headless, args.ident, args.output, args.block)
    elif args.action == "monitor":
        with connect_to_server() as connection: # might throw
            monitor_ids(connection, list( args.job_ids))
    elif args.action == "cancel":
        with connect_to_server() as connection: # might throw
            cancel_ids(connection, list( args.job_ids))
    elif args.action == "clear-queue":
        with connect_to_server() as connection: # might throw
            clear_queue(connection)
    elif args.action == "shutdown":
        with connect_to_server() as connection: # might throw
            shutdown_server(connection, force=args.force, finish_queue=args.finish_queue)
            


