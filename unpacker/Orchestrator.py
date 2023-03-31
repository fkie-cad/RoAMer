import datetime
import json
import logging
import os
import socket
import time
import traceback

from unpacker.Unpacker import Unpacker
from unpacker.winwrapper.utilities import prepareOperatingSystem
from utility.win_env import get_user_path


class Orchestrator:

    def __init__(self):
        self.userPath = get_user_path()
        self.config = None
        self.sample = None
        self.isLocalUnpacking = False
        self.sock = None
        self.unpacker = None
        # This one has to be imported so, that there is no interaction with the harddisk
        hackSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def set_local_unpacker(self, value):
        if value:
            logging.info("RoAMer set to local mode.")
        self.isLocalUnpacking = value

    def initiate(self, parameters):
        # init output libraries
        init_output = json.dumps({"key": "value"})
        init_output = json.dumps({"key": u"value"})
        # prepare execution
        with open(os.path.join(self.userPath, "sample"), "rb") as f_in:
            self.sample = f_in.read()
        self.unpacker = Unpacker(self.sample, parameters)
        prepareOperatingSystem(self.unpacker.config, self.unpacker.userPath)

    def send_output(self, output):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = (self.config["host_ip"], self.config["host_port"])
        logging.info("sending output to %s:%d", self.config["host_ip"], self.config["host_port"])
        self.sock.connect(server_address)
        self.sock.sendall(bytes(json.dumps(output), encoding="utf-8"))
        logging.info("closing communications")
        self.sock.shutdown(socket.SHUT_WR)
        self.sock.close()

    def check_if_dumps_present(self, output):
        return len(output["dumps"]) > 0

    def load_config(self):
        with open(os.path.join(self.userPath, "config"), "rb") as f_in:
            self.config = json.loads(f_in.read())

    def store_output(self, output):
        outputPath = self.userPath + "roamer_output" + os.sep + datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        logging.info("storing local output to: %s", outputPath)
        if not os.path.isdir(self.userPath + os.sep + "roamer_output"):
            os.makedirs(self.userPath + os.sep + "roamer_output")
        os.makedirs(outputPath)
        with open(outputPath + os.sep + "stats.json", "w") as fOutput:
            fOutput.write(json.dumps(output["4x5_hook_spoofuser"]["stats"], indent=1, sort_keys=True))
        with open(outputPath + os.sep + "observations.json", "w") as fOutput:
            fOutput.write(json.dumps(output["4x5_hook_spoofuser"]["observations"], indent=1, sort_keys=True))
        for dump in output["4x5_hook_spoofuser"]["dumps"]:
            fn = "%d_0x%08x.bin" % (dump["pid"], dump["base"])
            with open(outputPath + os.sep + fn, "w") as fOutput:
                fOutput.write(json.dumps(dump, indent=1, sort_keys=True))

    def run(self):
        results = {}
        self.load_config()
        if not self.isLocalUnpacking:
            self.send_output("RUNNING")
        try:
            for parameters in self.config["parameters"]:
                logging.info("starting with config")
                self.initiate(parameters)
                logging.info("Commence starting phase!")
                self.unpacker.starting_phase()
                logging.info("Commence monitoring phase!")
                self.unpacker.monitoring_phase()
                logging.info("Commence exporting phase!")
                output = self.unpacker.get_output()
                results[parameters["name"]] = output
                if self.check_if_dumps_present(output):
                    logging.info("We have some dumps, stopping execution of further parameter sets")
                    break
            if self.config["debug_sleep"]:
                logging.info("Before sending the output, you now have the chance to abort execution within %d seconds.",
                            self.config["debug_sleep"])
                time.sleep(self.config["debug_sleep"])
            results["log"] = ""
            with open(os.path.join(self.userPath, "roamer.log"), "r") as f_log:
                results["log"] = f_log.read()
            if self.isLocalUnpacking:
                self.store_output(results)
            else:
                self.send_output(results)
        except Exception as e:
            if not self.isLocalUnpacking:
                self.send_output(f"EXCEPTION from client:\n{traceback.format_exc()}")
            else:
                print(traceback.format_exc())
