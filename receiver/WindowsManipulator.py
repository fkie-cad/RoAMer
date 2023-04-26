import ctypes
from ctypes import wintypes

from receiver import injector_defines
import win32con
import win32process

KERNEL_32 = ctypes.windll.kernel32
ADVAPI_32 = ctypes.windll.advapi32


class WindowsManipulator:

    def create_process(self, path):
        _, _, process_id, _ = win32process.CreateProcess(None, path, None, None, 0, win32con.NORMAL_PRIORITY_CLASS, None, None, win32process.STARTUPINFO())
        return process_id

    def grant_debug_privilege(self, pid=0):
        """ grant SeDebugPrivilege to own process
        @param pid: Process id to set permissions of (or 0 if current)
        @type pid: int
        @return: True if operation was successful,
                  False otherwise
        """
        ADVAPI_32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
        ADVAPI_32.LookupPrivilegeValueW.argtypes = (wintypes.LPWSTR, wintypes.LPWSTR, ctypes.POINTER(injector_defines.LUID))
        ADVAPI_32.AdjustTokenPrivileges.argtypes = (wintypes.HANDLE,
                                                    wintypes.BOOL, ctypes.POINTER(injector_defines.TOKEN_PRIVILEGES),
                                                    wintypes.DWORD, ctypes.POINTER(injector_defines.TOKEN_PRIVILEGES),
                                                    ctypes.POINTER(wintypes.DWORD))

        # local or remote process?
        if pid == 0:
            h_process = KERNEL_32.GetCurrentProcess()
        else:
            h_process = KERNEL_32.OpenProcess(injector_defines.PROCESS_ALL_ACCESS, False, pid)

        if not h_process:
            print("Failed to open process for setting debug privileges" % str(pid))
            return False

        # obtain token to process
        h_current_token = wintypes.HANDLE()
        if not ADVAPI_32.OpenProcessToken(h_process, injector_defines.TOKEN_ALL_ACCESS, h_current_token):
            print("Did not obtain process token.")
            return False

        # look up current privilege value
        se_original_luid = injector_defines.LUID()
        if not ADVAPI_32.LookupPrivilegeValueW(None, "SeDebugPrivilege", se_original_luid):
            print("Failed to lookup privilege value.")
            return False

        luid_attributes = injector_defines.LUID_AND_ATTRIBUTES()
        luid_attributes.Luid = se_original_luid
        luid_attributes.Attributes = injector_defines.SE_PRIVILEGE_ENABLED
        token_privs = injector_defines.TOKEN_PRIVILEGES()
        token_privs.PrivilegeCount = 1
        token_privs.Privileges = luid_attributes

        if not ADVAPI_32.AdjustTokenPrivileges(h_current_token, False, token_privs, 0, None, None):
            print("Failed to grant SE_DEBUG_PRIVILEGE to self.")
            return False

        KERNEL_32.CloseHandle(h_current_token)
        KERNEL_32.CloseHandle(h_process)
        return True
