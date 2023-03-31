import base64
import json
import logging
import os
import socket
import time

from receiver.WindowsManipulator import WindowsManipulator
from utility.win_env import get_user_path

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)-15s %(message)s")


class Receiver:

    def __init__(self):
        self.user_path = get_user_path()
        self.sock = self._init_socket()
        self.win_manipulator = WindowsManipulator()

    def _init_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("0.0.0.0", 10000))
        sock.listen(1)
        return sock

    def _wait_for_host(self):
        LOG.debug("waiting...")
        conn, addr = self.sock.accept()
        return conn

    def _negotiate_needed_files(self, conn):
        necessary_files = str(conn.recv(1024), encoding="utf-8").split(",")
        LOG.info("received needed files")
        for file in os.listdir(self.user_path):
            if file in necessary_files:
                necessary_files.remove(file)
        if necessary_files:
            conn.sendall(bytes(",".join(necessary_files), encoding="utf-8"))
        else:
            conn.sendall(bytes("nothing", encoding="utf-8"))

    def _receive_data(self, conn):
        received_data = b""
        while True:
            data = conn.recv(1024 * 1024)
            if not data:
                break
            received_data += data
        LOG.debug("received everything")
        return str(received_data, encoding="utf-8")

    def _write_files(self, received_data):
        received_files = json.loads(received_data)
        self._write_b64_encoded_file("sample", received_files["sample"])
        self._write_b64_encoded_file("config", received_files["config"])
        for filename in received_files["unpacker"].keys():
            self._write_b64_encoded_file(filename, received_files["unpacker"][filename])

    def _write_b64_encoded_file(self, filename, data):
        with open(self.user_path + filename, "wb") as f_out:
            f_out.write(base64.b64decode(data))

    def run(self):
        conn = self._wait_for_host()
        self._negotiate_needed_files(conn)
        receivedData = self._receive_data(conn)
        LOG.debug("writing files...")
        self._write_files(receivedData)
        time.sleep(1)
        process_id = self.win_manipulator.create_process(os.path.join([self.user_path, "main.exe"]))
        time.sleep(1)
        self.win_manipulator.grant_debug_privilege(process_id)


def main():
    receiver = Receiver()
    receiver.run()


if __name__ == '__main__':
    main()
