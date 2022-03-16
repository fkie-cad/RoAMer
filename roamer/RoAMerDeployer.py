import base64
import json
import logging
import os
import socket
import time
import zipfile

from roamer.DumpPersister import persist_data
from roamer.VmController import VmController

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")



def zip_folder(path):
    zfName = 'roamer.zip'
    if os.path.exists(zfName):
        os.remove(zfName)
    with zipfile.ZipFile(zfName, 'w') as zf:
        # Adding files from directory 'files'
        for root, dirs, files in os.walk(path):
            for f in files:
                if f == zfName:
                    continue
                filename = os.path.join(root, f)
                arcname = os.path.relpath(filename, path)
                zf.write(filename, arcname=arcname)



class Deployer:

    def __init__(self, roamer_config, headless, vm, snapshot, ident):
        self.unpacker_config = roamer_config.UNPACKER_CONFIG
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

    def gather_data(self, source_folder):
        unpacker_files={}
        unpacker_files["sample"] = self._to_base64(b"empty because of update")
        unpacker_files["config"] = self._to_base64(bytes(json.dumps(self.unpacker_config), encoding="utf-8"))
        unpacker_files["unpacker"] = {
            "main.exe": self._get_content_of_file_as_base64(os.path.join(source_folder, "updater", "bin", "update_launcher.exe")),
            "updater.py": self._get_content_of_file_as_base64(os.path.join(source_folder, "updater", "updater.py")),
            # "main.exe": self._get_content_of_file_as_base64(os.path.join(source_folder, "updater", "bin", "updater.exe")),
            "roamer.zip": self._get_content_of_file_as_base64(os.path.join(source_folder, "roamer.zip")),
        }
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

    def communicate_with_receiver_force_send(self, unpacker_files):
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
        LOG.info("start sending")
        sock.sendall(bytes(json.dumps(unpacker_files), encoding="utf-8"))
        sock.shutdown(socket.SHUT_WR)
        sock.close()
        LOG.info("sending of unpacker completed.")
        return

    def communicate_with_updater(self):
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


    def deploy(self):

        source_folder = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        LOG.info("Zipping repo %s", source_folder)
        zip_folder(source_folder)

        updater_files = self.gather_data(source_folder)
        self.prepare_vm()
        self.communicate_with_receiver_force_send(updater_files)
        
        returned_raw_data = self.communicate_with_updater()
        if returned_raw_data:
            if returned_raw_data == b'"RUNNING"':
                LOG.info("Updater status: {}".format(returned_raw_data))
            else:
                LOG.warning("Updater status unknown, this should be investigated!")
                LOG.info("{}".format(returned_raw_data))
        # receive actual result output
        returned_raw_data = self.communicate_with_updater()
        if returned_raw_data:
            files = json.loads(returned_raw_data)
            unpacker = base64.b64decode(files["unpacker"])
            LOG.info("Write Unpacker")
            with open(os.path.join(source_folder, "roamer", "bin", "main.exe"), "wb") as file:
                file.write(unpacker)
        else:
            LOG.warning("No Data was send by the updater!")
        time.sleep(2)
        self.vm_controller.update_snapshot(self.vm_name, self.snapshotName)
        self.vm_controller.stop_vm(self.vm_name)
        time.sleep(5)







