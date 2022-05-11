import base64
import json
import logging
import os
import socket
import time

from roamer.DumpPersister import persist_data
from roamer.VmController import VmController

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")


class RoAMer:

    def __init__(self, roamer_config, headless, vm, snapshot, ident):
        self.unpacker_config = roamer_config.UNPACKER_CONFIG
        self.post_processing_config = roamer_config.POST_PROCESSING_CONFIG
        self.bins = roamer_config.BIN_ROOT
        self.vm_name = roamer_config.VM_NAME if not vm else vm
        self.snapshotName = roamer_config.SNAPSHOT_NAME if not snapshot else snapshot
        self.vm_controller = VmController.factory(roamer_config.VM_CONTROLLER, headless)
        self.sample = ""
        self.ident = ident

    def initiate_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock

    def gather_files_for_unpacker(self, sample_name):
        unpacker_files = {}
        unpacker_files["sample"] = self._get_content_of_file_as_base64(sample_name)
        unpacker_files["config"] = self._to_base64(bytes(json.dumps(self.unpacker_config), encoding="utf-8"))
        unpacker_files["unpacker"] = {}
        for root, _, filenames in os.walk(self.bins):
            for filename in filenames:
                unpacker_files["unpacker"][filename] = self._get_content_of_file_as_base64(os.path.join(root, filename))
        return unpacker_files

    def _to_base64(self, string):
        return str(base64.b64encode(string), encoding="utf-8")

    def _get_content_of_file_as_base64(self, path):
        with open(path, "rb") as f_in:
            content = f_in.read()
        return self._to_base64(content)

    def prepare_vm(self):
        LOG.info("preparing VM for RoAMer")
        try:
            self.vm_controller.stop_vm(self.vm_name)
        except:
            LOG.info("stopping VM failed... continuing...")
            pass
        self.vm_controller.set_snapshot(self.vm_name, self.snapshotName)
        self.vm_controller.start_vm(self.vm_name)
        LOG.info("VM %s should now be running on snapshot %s", self.vm_name, self.snapshotName)

    def communicate_with_receiver(self, unpacker_files):
        print((self.unpacker_config["guest_ip"], self.unpacker_config["guest_port"]))
        LOG.info("Connecting to roamer-receiver...")
        sock = self.initiate_socket()
        while True:
            try:
                sock.connect((self.unpacker_config["guest_ip"], self.unpacker_config["guest_port"]))
                break
            except socket.error:
                time.sleep(1)
        LOG.info("Sending file list...")
        sock.sendall(bytes(",".join(unpacker_files["unpacker"].keys()), encoding="utf-8"))
        LOG.info("waiting for needed files...")
        needed = sock.recv(1024 * 1024)
        print(needed)
        unavailableFiles = set(unpacker_files["unpacker"].keys()).difference(set(str(a, encoding="utf-8") for a in needed.split(b",")))
        for k in unavailableFiles:
            unpacker_files["unpacker"].pop(k)
        LOG.info("start sending")
        sock.sendall(bytes(json.dumps(unpacker_files), encoding="utf-8"))
        sock.shutdown(socket.SHUT_WR)
        sock.close()
        LOG.info("sending of unpacker completed.")
        return

    def communicate_with_unpacker(self):
        sock = self.initiate_socket()
        sock.bind((self.unpacker_config["host_ip"], self.unpacker_config["host_port"]))
        sock.listen(1)
        sock.settimeout(self.unpacker_config["socket_timeout"])
        LOG.info("waiting for connection")
        try:
            connection, client_address = sock.accept()
        except socket.timeout:
            LOG.debug("socket timed out...")
            return
        LOG.info('connection from %s', client_address)
        returned_data_raw = b""
        try:
            while True:
                data = connection.recv(1024 * 1024)
                if not data:
                    break
                returned_data_raw += data
            return returned_data_raw
        finally:
            connection.close()
            sock.close()

    def run_folder(self, target_path, output_folder = None):
        for filename in os.listdir(target_path):
            sample = os.path.join(target_path, filename)
            if os.path.isfile(sample):
                self.run_file(sample, output_folder=output_folder)

    def run_file(self, target_path, output_folder = None):
        LOG.info("Unpacking %s", target_path)
        unpacker_files = self.gather_files_for_unpacker(target_path)
        self.prepare_vm()
        self.communicate_with_receiver(unpacker_files)
        # receive status from unpacker
        returned_raw_data = self.communicate_with_unpacker()
        if returned_raw_data:
            if returned_raw_data == b'"RUNNING"':
                LOG.info("Unpacker status: {}".format(returned_raw_data))
            elif returned_raw_data.startswith(b'"EXCEPTION'):
                LOG.error(json.loads(returned_raw_data))
            else:
                LOG.warning("Unpacker status unknown, this should be investigated!")
                LOG.info("{}".format(returned_raw_data))
        # receive actual result output
        returned_raw_data = self.communicate_with_unpacker()
        if returned_raw_data:
            if returned_raw_data.startswith(b'"EXCEPTION'):
                LOG.error(json.loads(returned_raw_data))
            else:
                LOG.info("persisting dumps ...")
                if output_folder is None:
                    output_path = target_path
                else:
                    output_path = os.path.join(output_folder, os.path.basename(target_path))
                persist_data(output_path, json.loads(returned_raw_data), self.ident, self.post_processing_config)
        else:
            LOG.info("Nothing returned by unpacker")
        self.vm_controller.stop_vm(self.vm_name)
        time.sleep(5)

    def run(self, target_path, output_folder = None):
        try:
            if os.path.isdir(target_path):
                self.run_folder(target_path, output_folder=output_folder)
            elif os.path.isfile(target_path):
                self.run_file(target_path, output_folder=output_folder)
            else:
                LOG.error("Target was neither file nor directory, aborting.")
        except Exception:
            LOG.exception("uncaught exception")
