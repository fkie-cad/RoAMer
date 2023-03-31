import argparse
import base64
import json
import time
import zipfile
import os
import shutil
import socket
import subprocess
import traceback
import logging
from ctypes import windll
from utility.win_env import get_user_path


def extract(zip_path, target_path):
    if os.path.exists(target_path):
        shutil.rmtree(target_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_path)
    os.remove(zip_path)


def send_keycode(key_code):
    windll.user32.keybd_event(key_code, 0x45, 1 | 0, 0)
    windll.user32.keybd_event(key_code, 0x45, 1 | 2, 0)


class Updater:
    def __init__(self):
        self.userPath = get_user_path()
        self.config = None
        with open(os.path.join(self.userPath, "config"), "rb") as f_in:
            self.config = json.loads(f_in.read())
        paths = self.config["client_paths"]
        self.roamerRepoPath = paths["repo"]
        self.roamerZipPath = paths["repo_zip"]
        self.receiverPath = paths["receiver"]
        self.toWhitelistPath = paths["to_whitelist"]
        self.sample = None
        self.tasks = self.config["tasks"]
        self.isLocalUnpacking = False
        self.sock = None
        self.unpacker = None
        # This one has to be imported so, that there is no interaction with the harddisk
        hackSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def set_local_unpacker(self, value):
        if value:
            logging.info("RoAMer Updater set to local mode.")
        self.isLocalUnpacking = value

    def send_output(self, output):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = (self.config["host_ip"], self.config["host_port"])
        logging.info(
            "sending output to %s:%d", self.config["host_ip"], self.config["host_port"]
        )
        self.sock.connect(server_address)
        self.sock.sendall(bytes(json.dumps(output), encoding="utf-8"))
        logging.info("closing communications")
        self.sock.shutdown(socket.SHUT_WR)
        self.sock.close()

    def send_nothing(self):
        self.send_output("empty")

    def extract_source(self):
        logging.info("Remove old repo before extracting source")
        self.cleanup([self.roamerRepoPath])
        logging.info("Extract source code")
        extract(self.roamerZipPath, self.roamerRepoPath)

    def compile_source(self):
        logging.info("Compile source code")
        compile_process = subprocess.Popen(
            os.path.join(self.roamerRepoPath, "compile.bat", cwd=self.roamerRepoPath)
        )
        compile_process.wait()

    def restart_receiver(self, clear_screen=True):
        logging.info("Restart the Receiver")
        send_keycode(0x0D)  # Enter

        if clear_screen:
            send_keycode(ord("C"))
            send_keycode(ord("L"))
            send_keycode(ord("S"))
            send_keycode(0x0D)  # Enter
            send_keycode(0x26)  # Up

        # restart roamer receiver
        send_keycode(0x26)  # Up
        send_keycode(0x0D)  # Enter

    def remove_this_script(self):
        if self.config["staged_update"]:
            logging.info("Remove this update script")
            os.remove(os.path.join([self.userPath, "main.exe"]))
            os.remove(os.path.abspath(__file__))
        else:
            logging.info("Remove this executable")
            tmp_bat_path = os.path.join([self.userPath, "tmp.bat"])
            self_delete_cmd = f"""
                @echo off
                :start
                if exist {os.path.join([self.userPath, "main.exe"])} goto delete
                del {tmp_bat_path}
                :delete
                del {os.path.join([self.userPath, "main.exe"])}
                goto start
            """
            with open(tmp_bat_path, "w") as f:
                f.write(self_delete_cmd)
            subprocess.Popen(f"cmd /c {tmp_bat_path}", stdout=None)

    def update_whitelist(self, executable_path):
        self.cleanup([os.path.join([self.userPath, "pe_header_whitelist.json"])])
        subprocess.Popen(
            [executable_path, os.path.join(["C:"])], cwd=self.userPath
        ).wait()

    def replace_receiver(self, source):
        logging.info("Replace Receiver")
        shutil.copy(source, self.receiverPath)

    def _to_base64(self, string):
        return str(base64.b64encode(string), encoding="utf-8")

    def _get_content_of_file_as_base64(self, path):
        with open(path, "rb") as f_in:
            content = f_in.read()
        return self._to_base64(content)

    def gather_data_and_send(self):
        logging.info("Send back binaries to Host")
        result = {}
        if "compile_on_client" in self.tasks:
            result.update(
                {
                    "unpacker": self._get_content_of_file_as_base64(
                        os.path.join([self.roamerRepoPath, "unpacker","dist","main.exe"])
                    ),
                    "receiver": self._get_content_of_file_as_base64(
                        os.path.join([self.roamerRepoPath, "receiver","dist","main.exe"])
                    ),
                    "whitelister": self._get_content_of_file_as_base64(
                        os.path.join([self.roamerRepoPath,"whitelister","dist","PEHeaderWhitelister.exe"])
                    ),
                    "update_launcher": self._get_content_of_file_as_base64(
                        os.path.join([self.roamerRepoPath, "updater", "dist", "update_launcher.exe"])
                    ),
                    "updater": self._get_content_of_file_as_base64(
                        os.path.join([self.roamerRepoPath, "updater", "dist", "updater.exe"])
                    ),
                }
            )
        if "whitelist" in self.tasks:
            result["pe_header_whitelist.json"] = self._get_content_of_file_as_base64(
                os.path.join([self.userPath,  "pe_header_whitelist.json"])
            )

        if len(result) != 0:
            self.send_output(result)
        else:
            self.send_nothing()

    def cleanup(self, list):
        for entry in list:
            if not os.path.exists(entry):
                continue
            if os.path.isfile(entry):
                os.remove(entry)
            elif os.path.isdir(entry):
                shutil.rmtree(entry)

    def run(self):
        results = {}
        # self.load_config()
        start_time = time.time()
        receiver_termination_duration = 4
        strict_cleanup_list = [
            os.path.join([self.userPath, "config"]),
            os.path.join([self.userPath, "sample"]),
        ]

        if not self.isLocalUnpacking:
            self.send_output("RUNNING")

        try:
            if "compile_on_client" in self.tasks:
                self.extract_source()
                self.compile_source()
                receiver_source_path = os.path.join([self.roamerRepoPath, "receiver", "dist", "main.exe"])
                whitelister_source_path = (
                    os.path.join([self.roamerRepoPath, "whitelister", "dist", "PEHeaderWhitelister.exe"])
                )
                strict_cleanup_list += [self.roamerRepoPath, self.roamerZipPath]

            if "receiver_bin_to_client" in self.tasks:
                receiver_source_path = os.path.join([self.userPath, "new_receiver.exe"])
                strict_cleanup_list += [receiver_source_path]

            if "overwrite_receiver" in self.tasks:
                now = time.time()
                sleep_time = start_time + receiver_termination_duration - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.replace_receiver(receiver_source_path)

            if "whitelister_bin_to_client" in self.tasks:
                whitelister_source_path = os.path.join([self.userPath, "whitelister.exe"])
                strict_cleanup_list += [whitelister_source_path]

            if "whitelist" in self.tasks:
                self.update_whitelist(whitelister_source_path)

            if not self.isLocalUnpacking:
                self.gather_data_and_send()

            if "reinit_and_store" in self.tasks:
                if self.config["requires_cleaning_before_snapshot"]:
                    self.cleanup(strict_cleanup_list)
                self.remove_this_script()
                self.restart_receiver()

        except Exception as e:
            if not self.isLocalUnpacking:
                self.send_output(f"EXCEPTION from client:\n{traceback.format_exc()}")
            else:
                print(traceback.format_exc())


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)-15s %(levelname)-7s %(module)s.%(funcName)s(): %(message)s",
        level=logging.DEBUG,
    )

    parser = argparse.ArgumentParser(description="RoAMer Update Module.")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run the updater locally and don't send back results.",
    )
    args = parser.parse_args()
    updater = Updater()
    updater.set_local_unpacker(args.local)
    updater.run()
