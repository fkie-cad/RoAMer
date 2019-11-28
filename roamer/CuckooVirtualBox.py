# Copyright (C) 2010-2013 Claudio Guarnieri.
# Copyright (C) 2014-2016 Cuckoo Foundation.
# This file was part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# Edited by Daniel Plohmann for needs in RoAMer
# See the file 'docs/LICENSE' for copying permission.

import logging
import re
import time
import subprocess

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")


class CuckooVirtualBox(object):
    """Virtualization layer for VirtualBox."""

    # VM states.
    SAVED = "saved"
    RUNNING = "running"
    POWEROFF = "poweroff"
    ABORTED = "aborted"
    ERROR = "machete"

    def __init__(self, headless):
        self.vbox_manage_path = "/usr/bin/VBoxManage"
        self.status = None
        if headless:
            self.mode = "headless"
        else:
            self.mode = "gui"

    def setSnapshot(self, vm_name, snapshot_name=None):
        """Reset virtual machine to a snapshot.
        @param vm_name: virtual machine name.
        @param task: task object.
        @raise Exception: if unable to start.
        """

        if self._status(vm_name) == self.RUNNING:
            raise Exception("Trying to start an already started vm %s" % vm_name)

        virtualbox_args = [self.vbox_manage_path, "snapshot", vm_name]
        if snapshot_name is not None:
            virtualbox_args.extend(["restore", snapshot_name])
        else:
            virtualbox_args.extend(["restorecurrent"])

        try:
            if subprocess.call(virtualbox_args,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               close_fds=True):
                raise Exception("VBoxManage exited with error restoring the machine's snapshot")
        except OSError as exc:
            raise Exception("VBoxManage failed restoring the machine: %s" % exc)

        self._waitStatus(vm_name, self.SAVED)

    def start(self, vm_name):
        """Start a virtual machine.
        @param vm_name: virtual machine name.
        @param task: task object.
        @raise Exception: if unable to start.
        """
        if self._status(vm_name) == self.RUNNING:
            raise Exception("Trying to start an already started vm %s" % vm_name)

        try:
            proc = subprocess.Popen([self.vbox_manage_path,
                                     "startvm",
                                     vm_name,
                                     "--type",
                                     self.mode],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
            _, err = proc.communicate()
            if err:
                raise OSError(err)
        except OSError as exc:
            raise Exception("VBoxManage failed starting the machine %s in mode: %s" % (vm_name, exc))

        self._waitStatus(vm_name, self.RUNNING)

    def stop(self, vm_name):
        """Stops a virtual machine.
        @param vm_name: virtual machine name.
        @raise CuckooMachineError: if unable to stop.
        """
        LOG.debug("Stopping vm %s" % vm_name)

        if self._status(vm_name) in [self.POWEROFF, self.ABORTED]:
            raise Exception("Trying to stop an already stopped vm %s" % vm_name)

        try:
            proc = subprocess.Popen([self.vbox_manage_path,
                                     "controlvm", vm_name, "poweroff"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
            # Sometimes VBoxManage stucks when stopping vm so we needed
            # to add a timeout and kill it after that.
            stop_me = 0
            while proc.poll() is None:
                if stop_me < 10:
                    time.sleep(1)
                    stop_me += 1
                else:
                    LOG.info("Stopping vm %s timeouted. Killing" % vm_name)
                    proc.terminate()

            if proc.returncode != 0 and stop_me < 10:
                LOG.error("VBoxManage exited with error powering off the machine")
        except OSError as exc:
            raise Exception("VBoxManage failed powering off the machine: %s" % exc)
        #self._waitStatus(vm_name, [self.POWEROFF, self.ABORTED, self.SAVED])

    def _list(self):
        """Lists virtual machines installed.
        @return: virtual machine names list.
        """
        try:
            proc = subprocess.Popen([self.vbox_manage_path,
                                     "list", "vms"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
            output, _ = proc.communicate()
        except OSError as exc:
            raise Exception("VBoxManage error listing installed machines: %s" % exc)

        machines = []
        for line in output.split("\n"):
            try:
                vm_name = line.split('"')[1]
                if vm_name == "<inaccessible>":
                    LOG.warn("Found an inaccessible virtual machine, please check its state.")
                else:
                    machines.append(vm_name)
            except IndexError:
                continue

        return machines

    def _status(self, vm_name):
        """Gets current status of a vm.
        @param vm_name: virtual machine name.
        @return: status string.
        """
        LOG.debug("Getting status for %s" % vm_name)
        status = None
        try:
            proc = subprocess.Popen([self.vbox_manage_path,
                                     "showvminfo",
                                     vm_name,
                                     "--machinereadable"],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
            output, err = proc.communicate()
            output = output.decode(encoding="utf-8")

            if proc.returncode != 0:
                # It's quite common for virtualbox crap utility to exit with:
                # VBoxManage: error: Details: code E_ACCESSDENIED (0x80070005)
                # So we just log to debug this.
                LOG.error("VBoxManage returns error checking status for machine %s: %s", vm_name, err)
                status = self.ERROR
        except OSError as exc:
            LOG.error("VBoxManage failed to check status for machine %s: %s", vm_name, exc)
            status = self.ERROR
        if not status:
            for line in output.split("\n"):
                state = re.match(r'VMState="(\w+)"', line, re.M | re.I)
                if state:
                    status = state.group(1)
                    LOG.debug("Machine %s status %s" % (vm_name, status))
                    status = status.lower()
        # Report back status.
        if status:
            self.status = status
            return status
        else:
            raise Exception("Unable to get status for %s" % vm_name)

    def _waitStatus(self, vm_name, state):
        """Waits for a vm status.
        @param vm_name: virtual machine name.
        @param state: virtual machine status, accepts multiple states as list.
        @raise CuckooMachineError: if default waiting timeout expire.
        """
        # This block was originally suggested by Loic Jaquemet.
        waitme = 0
        try:
            current = self._status(vm_name)
        except NameError:
            return

        if isinstance(state, str):
            state = [state]

        while current not in state:
            LOG.debug("Waiting %i cuckooseconds for machine %s to switch to status %s", waitme, vm_name, state)
            if waitme > 10:
                raise Exception("Timeout hit while for machine %s to change status", vm_name)
            time.sleep(1)
            waitme += 1
        self._status(vm_name)
