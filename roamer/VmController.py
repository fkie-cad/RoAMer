import logging
import time
import datetime

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)-15s %(message)s")


TIMEOUT = 20


class VmController(object):

    def factory(controller_type, headless):
        if controller_type == "VboxApiController":
            return VboxApiController(headless)
        if controller_type == "VboxManageController":
            return VboxManageController(headless)
        if controller_type == "KvmManageController":
            return KvmManageController()
        assert 0, "No implementation for " + controller_type
    factory = staticmethod(factory)

    def stop_vm(self, vm_name):
        raise NotImplementedError

    def set_snapshot(self, vm_name, snapshot_name):
        raise NotImplementedError

    def start_vm(self, vm_name):
        raise NotImplementedError


class KvmManageController(VmController):
    def __init__(self):
        import libvirt
        self.libvirt = libvirt

    def stop_vm(self, vm_name):
        with self.libvirt.open(None) as conn:
            vm = conn.lookupByName(vm_name)
            vm.destroy()

    def set_snapshot(self, vm_name, snapshot_name):
        with self.libvirt.open(None) as conn:
            vm = conn.lookupByName(vm_name)
            snapshot = vm.snapshotLookupByName(snapshot_name)
            vm.revertToSnapshot(snapshot)

    def start_vm(self, vm_name):
        # This function is not needed, as libvirt already runs the VM when setting the snapshot unlike VBOX
        pass


class VboxManageController(VmController):

    def __init__(self, headless):
        from roamer.CuckooVirtualBox import CuckooVirtualBox
        self.cuckoo_virtualbox = CuckooVirtualBox(headless)

    def stop_vm(self, vm_name):
        LOG.debug("MOCK: stopVm %s", vm_name)
        self.cuckoo_virtualbox.stop(vm_name)

    def set_snapshot(self, vm_name, snapshot_name):
        LOG.debug("MOCK: setSnapshot %s %s", vm_name, snapshot_name)
        self.cuckoo_virtualbox.setSnapshot(vm_name, snapshot_name)
    
    def update_snapshot(self, vm_name, snapshot_name, keep_old=True):
        LOG.debug("MOCK: setSnapshot %s %s", vm_name, snapshot_name)
        name_for_old_state = snapshot_name+"_old_"+datetime.datetime.utcnow().isoformat()
        self.cuckoo_virtualbox.renameSnapshot(vm_name, name_for_old_state, snapshot_name)
        self.cuckoo_virtualbox.takeSnapshot(vm_name, snapshot_name)
        if not keep_old:
            self.cuckoo_virtualbox.deleteSnapshot(name_for_old_state)

    def start_vm(self, vm_name):
        LOG.debug("MOCK: startVm %s", vm_name)
        self.cuckoo_virtualbox.start(vm_name)


class VboxApiController(VmController):

    def __init__(self, headless):
        import vboxapi
        self.vboxapi = vboxapi
        if headless:
            self.mode = "headless"
        else:
            self.mode = "gui"

    def _getVboxVmHandle(self, vm_name):
        manager = self.vboxapi.VirtualBoxManager(None, None)
        return manager.vbox.findMachine(vm_name)

    def _getVboxSessionHandle(self):
        manager = self.vboxapi.VirtualBoxManager(None, None)
        return manager.mgr.getSessionObject(manager.vbox)

    def start_vm(self, vm_name):
        session = self._getVboxSessionHandle()
        vm = self._getVboxVmHandle(vm_name)
        while 1:
            try:
                session.unlockMachine()
                break
            except:
                time.sleep(5)
        vmstart = vm.launchvmProcess(session, self.mode, "")
        vmstart.waitForCompletion(TIMEOUT)

    def set_snapshot(self, vm_name, snapshot_name):
        session = self._getVboxSessionHandle()
        vm = self._getVboxVmHandle(vm_name)
        snap = vm.findSnapshot(snapshot_name)
        while 1:
            try:
                vm.lockMachine(session, 1)
                break
            except:
                time.sleep(5)
        progress = session.console.restoreSnapshot(snap)
        progress.waitForCompletion(TIMEOUT)

    def stop_vm(self, vm_name):
        session = self._getVboxSessionHandle()
        vm = self._getVboxVmHandle(vm_name)
        while 1:
            try:
                vm.lockMachine(session, 1)
                shutdownprog = session.console.powerDown()
                shutdownprog.waitForCompletion(TIMEOUT)
                break
            except:
                time.sleep(5)
