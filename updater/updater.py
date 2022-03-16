import argparse
import base64
import json
import zipfile
import os
import shutil
import socket
import subprocess
import logging
from ctypes import windll


def extract(zip_path, target_path):
    if os.path.exists(target_path):
        shutil.rmtree(target_path)
    with zipfile.ZipFile(zip_path,"r") as zf:
        zf.extractall(target_path)
    os.remove(zip_path)

def send_keycode(key_code):
    windll.user32.keybd_event(key_code, 0x45, 1 | 0, 0)
    windll.user32.keybd_event(key_code, 0x45, 1 | 2, 0)


class Updater:

    def __init__(self):
        self.userPath = "C:\\Users\\%s\\" % os.getenv("username")
        self.roamerRepoPath = self.userPath + "roamer_repo"
        self.roamerZipPath = self.userPath + "roamer.zip"
        self.receiverPath = self.userPath + "Desktop\\roamer.exe"
        self.config = None
        self.sample = None
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
        logging.info("sending output to %s:%d", self.config["host_ip"], self.config["host_port"])
        self.sock.connect(server_address)
        self.sock.sendall(bytes(json.dumps(output), encoding="utf-8"))
        logging.info("closing communications")
        self.sock.shutdown(socket.SHUT_WR)
        self.sock.close()

    def load_config(self):
        with open(os.path.join(self.userPath, "config"), "rb") as f_in:
            self.config = json.loads(f_in.read())
    
    def extract_source(self):
        extract(self.roamerZipPath, self.roamerRepoPath)

    def compile_source(self):
        compile_process = subprocess.Popen(self.roamerRepoPath+"\\compile.bat", cwd=self.roamerRepoPath)
        compile_process.wait()

    def restart_receiver(self, clear_screen=True):
        send_keycode(0x0D) # Enter

        if clear_screen:
            send_keycode(ord("C"))
            send_keycode(ord("L"))
            send_keycode(ord("S"))
            send_keycode(0x0D) # Enter
            send_keycode(0x26) # Up

        # restart roamer receiver
        send_keycode(0x26) # Up
        send_keycode(0x0D) # Enter

    def remove_this_script(self):
        os.remove(os.path.abspath(__file__))

    def update_whitelist(self):
        subprocess.Popen(self.roamerRepoPath+"\\whitelister\\dist\\PEHeaderWhitelister.exe C:\\", cwd=self.roamerRepoPath+"\\whitelister").wait()
        shutil.move(self.roamerRepoPath+"\\whitelister\\pe_header_whitelist.json", self.userPath+"pe_header_whitelist.json")

    def copy_binaries(self, store_unpacker_at_userpath=True):
        if store_unpacker_at_userpath:
            # copy roamer unpacker
            shutil.copy(self.roamerRepoPath+"\\unpacker\\dist\\main.exe", self.userPath+"main.exe")
        else:
            os.remove(self.userPath+"main.exe")
        # copy roamer receiver
        shutil.copy(self.roamerRepoPath+"\\receiver\\dist\\main.exe", self.receiverPath)

    def _to_base64(self, string):
        return str(base64.b64encode(string), encoding="utf-8")

    def _get_content_of_file_as_base64(self, path):
        with open(path, "rb") as f_in:
            content = f_in.read()
        return self._to_base64(content)

    def send_binaries(self):
        result = {
            "unpacker": self._get_content_of_file_as_base64(self.roamerRepoPath+"\\unpacker\\dist\\main.exe"),
            "receiver": self._get_content_of_file_as_base64(self.roamerRepoPath+"\\receiver\\dist\\main.exe"),
            "whitelister": self._get_content_of_file_as_base64(self.roamerRepoPath+"\\whitelister\\dist\\PEHeaderWhitelister.exe"),
            "update_launcher": self._get_content_of_file_as_base64(self.roamerRepoPath+"\\updater\\dist\\update_launcher.exe"),
        }
        self.send_output(result)

    def run(self):
        results = {}
        self.load_config()
        if not self.isLocalUnpacking:
            self.send_output("RUNNING")
        logging.info("Extract source code")
        self.extract_source()
        logging.info("Compile source code")
        self.compile_source()
        logging.info("Copy binaries to targets")
        self.copy_binaries(store_unpacker_at_userpath=True)
        if not self.isLocalUnpacking:
            logging.info("Send back binaries to Host")
            self.send_binaries()
        logging.info("Remove this update script")
        self.remove_this_script()
        logging.info("Restart the Receiver")
        self.restart_receiver()



if __name__ == "__main__":
    logging.basicConfig(filename="C:\\Users\\{}\\roamerupdate.log".format(os.getenv("username")),
                        format="%(asctime)-15s %(levelname)-7s %(module)s.%(funcName)s(): %(message)s",
                        level=logging.DEBUG)

    parser = argparse.ArgumentParser(description='RoAMer Update Module.')
    parser.add_argument('--local', action='store_true', help='Run the updater locally and don\'t send back results.')
    args = parser.parse_args()
    updater = Updater()
    updater.set_local_unpacker(args.local)
    updater.run()