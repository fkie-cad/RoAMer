import base64
import json
import logging
import os
from re import I
import shutil
import socket
import time
import zipfile

from roamer.VmController import VmController

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")



def zip_folder(repo_path):
    zfName = 'roamer.zip'
    full_zip_path = os.path.join(repo_path, zfName)
    if os.path.exists(full_zip_path):
        os.remove(full_zip_path)
    with zipfile.ZipFile(full_zip_path, 'w') as zf:
        for root, dirs, files in os.walk(repo_path):
            for f in files:
                if f == zfName or f.endswith(".exe") or ".git" in root or "deployer_results" in root:
                    continue
                filename = os.path.join(root, f)
                arcname = os.path.relpath(filename, repo_path)
                zf.write(filename, arcname=arcname)

def remove_zip(repo_path):
    zfName = 'roamer.zip'
    full_zip_path = os.path.join(repo_path, zfName)
    if os.path.exists(full_zip_path):
        os.remove(full_zip_path)


def ExecuteDeployerTasks(roamer_config, tasks, headless, vm, snapshot, ident):
    if not tasks:
        tasks = roamer_config.TASKS

    if len(tasks) == 0:
        LOG.info("No task specified, nothing to do")
        return
    else:
        LOG.info(f"Tasks: {', '.join(tasks)}")

    try:
        tasks.remove("all")
        tasks += ["unpacker", "receiver", "whitelister", "whitelist", "bootstrap"]
    except ValueError:
        pass
    
    single_setup = (roamer_config.BUILD_INSTANCE == roamer_config.PROD_INSTANCE)
    build_subtasks = set()
    prod_subtasks = set()
    for task in tasks:
        if task=="unpacker":
            build_subtasks.update(["compile_on_client", "overwrite_unpacker"])
        elif task=="receiver":
            build_subtasks.update(["compile_on_client", "overwrite_receiver", "reinit_and_store"])
            if not single_setup:
                prod_subtasks.update(["receiver_bin_to_client", "overwrite_receiver", "reinit_and_store"])
        elif task=="whitelister":
            build_subtasks.update(["compile_on_client", "overwrite_whitelister"])
        elif task=="whitelist":
            if single_setup:
                build_subtasks.update(["compile_on_client", "whitelist", "reinit_and_store"])
            else:
                prod_subtasks.update(["whitelister_bin_to_client", "whitelist", "reinit_and_store"])
        elif task=="bootstrap":
            build_subtasks.update(["compile_on_client", "overwrite_updater"])
        else:
            LOG.error("Unknown task %s, Exiting", task)
            return
    if build_subtasks:
        LOG.info("Run Deployer on Build Snapshot")
        LOG.info(f"subtaks: {', '.join(build_subtasks)}")
        Deployer(roamer_config, roamer_config.BUILD_INSTANCE, build_subtasks, headless, vm, snapshot, ident).deploy()
    if prod_subtasks:
        LOG.info("Run Deployer on Prod Snapshot")
        LOG.info(f"subtaks: {', '.join(prod_subtasks)}")
        Deployer(roamer_config, roamer_config.PROD_INSTANCE, prod_subtasks, headless, vm, snapshot, ident).deploy()


class Deployer:

    def __init__(self, roamer_config, instance_config, tasks, headless, vm, snapshot, ident):
        self.deployer_config = instance_config
        self.tasks = list(tasks)
        self.bins = roamer_config.BIN_ROOT
        self.source_folder = roamer_config.PROJECT_ROOT
        self.vm_name = instance_config["VM_NAME"] if not vm else vm
        self.snapshotName = instance_config["SNAPSHOT_NAME"] if not snapshot else snapshot
        self.vm_controller = VmController.factory(instance_config["VM_CONTROLLER"], headless)
        self.sample = ""
        self.ident = ident

    def initiate_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock

    def _select_files_to_send(self):
        files_to_send = {}
        if self.deployer_config["staged_update"]:
            files_to_send["main.exe"] = "updater/bin/update_launcher.exe"
            files_to_send["updater.py"] = "updater/updater.py"
        else: 
            files_to_send["main.exe"] = "updater/bin/updater.exe"

        if "compile_on_client" in self.tasks:
            files_to_send["roamer.zip"] = "roamer.zip"

        if "receiver_bin_to_client" in self.tasks:
            files_to_send["new_receiver.exe"] = "deployer_results/receiver"

        if "whitelister_bin_to_client" in self.tasks:
            files_to_send["whitelister.exe"] = "whitelister/bin/PEHeaderWhitelister.exe"
        return files_to_send

    def gather_data(self):
        unpacker_files={}
        unpacker_files["sample"] = self._to_base64(b"empty because of update")
        config = dict(**self.deployer_config, tasks=self.tasks) # add tasks to config
        unpacker_files["config"] = self._to_base64(bytes(json.dumps(config), encoding="utf-8"))
        files_dict = {}
        for key, val in self._select_files_to_send().items():
            files_dict[key] = self._get_content_of_file_as_base64(os.path.join(self.source_folder, *val.split("/")))
        unpacker_files["unpacker"] = files_dict
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
        print((self.deployer_config["guest_ip"], self.deployer_config["guest_port"]))
        LOG.info("Connecting to roamer-receiver...")
        sock = self.initiate_socket()
        while True:
            try:
                sock.connect((self.deployer_config["guest_ip"], self.deployer_config["guest_port"]))
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
        LOG.info("sending of updater completed.")
        return

    def communicate_with_updater(self):
        sock = self.initiate_socket()
        sock.bind((self.deployer_config["host_ip"], self.deployer_config["host_port"]))
        sock.listen(1)
        sock.settimeout(self.deployer_config["socket_timeout"])
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

        if "compile_on_client" in self.tasks:
            LOG.info("Zipping repo %s", self.source_folder)
            zip_folder(self.source_folder)

        updater_files = self.gather_data()

        self.prepare_vm()
        self.communicate_with_receiver_force_send(updater_files)

        if "compile_on_client" in self.tasks:
            remove_zip(self.source_folder)
        
        returned_raw_data = self.communicate_with_updater()
        if returned_raw_data:
            if returned_raw_data == b'"RUNNING"':
                LOG.info("Updater status: {}".format(returned_raw_data))
            else:
                LOG.warning("Updater status unknown, this should be investigated!")
                LOG.info("{}".format(returned_raw_data))

        # receive actual result output
        returned_raw_data = self.communicate_with_updater()
        if returned_raw_data and returned_raw_data!=b'"empty"':
            files = json.loads(returned_raw_data)
            results_folder = os.path.join(self.source_folder, "deployer_results")
            if os.path.exists(results_folder):
                LOG.info("Clear deployer_results folder")
                shutil.rmtree(results_folder)
            os.mkdir(results_folder)

            LOG.info("Write received files into deployer_results")
            for name, data in files.items():
                decoded_data = base64.b64decode(data)
                with open(os.path.join(results_folder, name), "wb") as file:
                    file.write(decoded_data)

            if "overwrite_unpacker" in self.tasks:
                shutil.copyfile(os.path.join(results_folder, "unpacker"), os.path.join(self.source_folder, "roamer", "bin", "main.exe"))

            if "overwrite_whitelister" in self.tasks:
                os.makedirs(os.path.join(self.source_folder, "whitelister", "bin"), exist_ok=True)
                shutil.copyfile(os.path.join(results_folder, "whitelister"), os.path.join(self.source_folder, "whitelister", "bin", "PEHeaderWhitelister.exe"))
            
            if "overwrite_updater" in self.tasks:
                os.makedirs(os.path.join(self.source_folder, "updater", "bin"), exist_ok=True)
                shutil.copyfile(os.path.join(self.source_folder, "updater", "bin", "update_launcher.exe"), os.path.join(self.source_folder, "updater", "bin", "update_launcher_backup.exe"))
                shutil.copyfile(os.path.join(results_folder, "update_launcher"), os.path.join(self.source_folder, "updater", "bin", "update_launcher.exe"))
                shutil.copyfile(os.path.join(results_folder, "updater"), os.path.join(self.source_folder, "updater", "bin", "updater.exe"))
        else:
            LOG.warning("No Data was send by the updater!")
        time.sleep(2)
        if "reinit_and_store" in self.tasks:
            LOG.info("Take new snapshot")
            self.vm_controller.update_snapshot(self.vm_name, self.snapshotName)
        self.vm_controller.stop_vm(self.vm_name)
        time.sleep(5)







