import os
from ctypes import *
from ctypes.wintypes import *
import copy
import subprocess
import traceback
import winreg
import win32con
import win32process
import pefile

import logging.config


"""
SOURCES:
    http://www.rohitab.com/discuss/topic/39525-process-memory-scannerpy/
    http://code.activestate.com/recipes/305279/
    x64dbg
"""

class MEMORY_BASIC_INFORMATION64(Structure):
    _fields_ = [
        ("BaseAddress", c_ulonglong),
        ("AllocationBase", c_ulonglong),
        ("AllocationProtect", DWORD),
        ("__alignment1", DWORD),
        ("RegionSize", c_ulonglong),
        ("State", DWORD),
        ("Protect", DWORD),
        ("Type", DWORD),
        ("__alignment2", DWORD)]


class SYSTEM_INFO(Structure):
    _fields_ = [("wProcessorArchitecture", WORD),
                ("wReserved", WORD),
                ("dwPageSize", DWORD),
                ("lpMinimumApplicationAddress", DWORD),
                ("lpMaximumApplicationAddress", DWORD),
                ("dwActiveProcessorMask", DWORD),
                ("dwNumberOfProcessors", DWORD),
                ("dwProcessorType", DWORD),
                ("dwAllocationGranularity", DWORD),
                ("wProcessorLevel", WORD),
                ("wProcessorRevision", WORD)]


class SYSTEMTIME(Structure):
    _fields_ = [("wYear", WORD),
                ("wMonth", WORD),
                ("wDayOfWeek", WORD),
                ("wDay", WORD),
                ("wHour", WORD),
                ("wMinute", WORD),
                ("wSecond", WORD),
                ("wSecond", WORD)]


class Module_Info(Structure):
    _fields_ = [
        ("lpBaseOfDll", c_void_p),
        ("SizeOfImage", DWORD),
        ("EntryPoint", c_void_p)]


def open_process(pid):
    try:
        phandle = windll.kernel32.OpenProcess(0x0400 | 0x0010,
                                              False, pid)
    except:
        traceback.print_exc()
        logging.error("Failed to obtain process handle for PID: %d", pid)
        return 0
    return phandle


def enum_processes():
    cb_needed = c_ulong()
    lpid_process = (c_ulong * 256)()
    if windll.psapi.EnumProcesses(byref(lpid_process), sizeof(lpid_process), byref(cb_needed)):
        n_returned = int(cb_needed.value / sizeof(c_ulong()))
        pid_processes = [i for i in lpid_process][:n_returned]
    else:
        logging.exception("uncaught exception")
        return []
    return pid_processes


class _PROCESS_INFORMATION(Structure):
    _fields = [
        ("hProcess", HANDLE),
        ("hThread", HANDLE),
        ("dwProcessId", DWORD),
        ("dwThreadId", DWORD),
    ]


def create_process(path_to_program):
    PI = _PROCESS_INFORMATION()
    if windll.kernel32.CreateProcess(path_to_program, None, None, None, False, 0x04000000, None, None,
                                     subprocess.STARTUPINFO(), byref(PI)):
        return PI.hProcess, PI.hThread, PI.dwProcessId, PI.dwThreadId
    else:
        traceback.print_exc()
        return 0


def virtual_query_ex(process_handle, address):
    MBI = MEMORY_BASIC_INFORMATION64()
    MBI_pointer = byref(MBI)
    size = sizeof(MBI)
    lpaddress = c_void_p(address)
    if windll.kernel32.VirtualQueryEx(process_handle, lpaddress, MBI_pointer, size):
        return (MBI.BaseAddress, MBI.AllocationBase, MBI.AllocationProtect, 0,
                MBI.RegionSize, MBI.State, MBI.Protect, MBI.Type, 0)
    else:
        return 0


def enum_process_modules(hProcess):
    size = 0x10000
    lpcb_needed = DWORD(size)
    lph_module = (c_longlong * 5000)()
    while True:
        if windll.psapi.EnumProcessModulesEx(hProcess, byref(lph_module), lpcb_needed, byref(lpcb_needed), 0x03):
            needed = lpcb_needed.value
            if needed <= size:
                break
            size = needed
        else:
            traceback.print_exc()
            return []
    nReturned = int(lpcb_needed.value / sizeof(c_longlong))
    return [i for i in lph_module][:nReturned]


def getModuleFileName(hProcess, hModule):
    modname = (c_wchar * 256)()
    if windll.psapi.GetModuleFileNameExW(hProcess, cast(hModule, HMODULE), modname, 256 * 2):
        utf8EnsuredName = str(modname.value)
        try:
            utf8EnsuredName.encode("UTF8")
        except UnicodeEncodeError:
            utf8EnsuredName = "non-utf8:" + utf8EnsuredName.encode("hex")
        return utf8EnsuredName
    else:
        return ""


def getModuleInformation(hProcess, hModule):
    MI = Module_Info()
    if windll.psapi.GetModuleInformation(hProcess, cast(hModule, HMODULE), byref(MI), sizeof(MI)):
        return MI.lpBaseOfDll, MI.SizeOfImage, MI.EntryPoint
    else:
        logging.exception("uncaught exception")
        return ()


def getModulesForPid(pid):
    hProcess = open_process(pid)
    hModules = enum_process_modules(hProcess)
    modules = {}
    modules[pid] = set()
    for hModule in hModules:
        modules[pid].add((getModuleFileName(hProcess, hModule), getModuleInformation(hProcess, hModule)))
    return modules


def getAllModules():
    modules = {}
    pids = enum_processes()
    for pid in pids:
        hProcess = open_process(pid)
        if not hProcess:
            continue
        modules[pid] = set()
        hModules = enum_process_modules(hProcess)
        for hModule in hModules:
            modules[pid].add((getModuleFileName(hProcess, hModule), getModuleInformation(hProcess, hModule)))
    return modules


def name_of_process(hProcess):
    hModule = c_ulong()
    count = c_ulong()
    modname = c_buffer(30)
    windll.psapi.EnumProcessModules(hProcess, byref(hModule), sizeof(hModule), byref(count))
    windll.psapi.GetModuleBaseNameA(hProcess, hModule.value, modname, sizeof(modname))
    return b"".join([i for i in modname if i != b'\x00'])


def read_memory(process_handle, address, size):
    cbuffer = c_buffer(size)
    if windll.kernel32.ReadProcessMemory(process_handle, cast(address, LPVOID), cbuffer, size, 0):
        return cbuffer.raw
    else:
        return b""


def place_hook_in_registry(path_to_hook, path_to_registry):
    registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path_to_registry, 0, winreg.KEY_WRITE)
    winreg.SetValueEx(registry_key, "AppInit_DLLs", 0, winreg.REG_SZ, path_to_hook)
    winreg.SetValueEx(registry_key, "LoadAppInit_DLLs", 0, winreg.REG_DWORD, 1)
    winreg.SetValueEx(registry_key, "RequireSignedAppInit_DLLs", 0, winreg.REG_DWORD, 0)
    winreg.CloseKey(registry_key)
    return


def launchProcess(path):
    win32process.CreateProcess(None, path, None, None, 0, win32con.NORMAL_PRIORITY_CLASS, None, None,
                               win32process.STARTUPINFO())


def returnMemorymapForAllProcesses():
    pidProcesses = enum_processes()
    memory_map = {}
    for pid in pidProcesses:
        hProcess = open_process(pid)
        if not hProcess:
            continue
        memory_map[pid] = set()
        pageStart = 0
        while True:
            information = virtual_query_ex(hProcess, pageStart)
            if information == 0:
                break
            # 0x10000 is MEM_FREE
            if information[5] != 0x10000:
                memory_map[pid].add(copy.deepcopy(information))
            newAddress = information[0] + information[4]
            if newAddress <= pageStart:
                break
            pageStart = newAddress
        windll.kernel32.CloseHandle(hProcess)
    return memory_map


def close_handle(handle):
    return windll.kernel32.CloseHandle(handle)


def return_memory_map_for_pid(pid):
    hProcess = open_process(pid)
    memory_map = {}
    memory_map[pid] = set()
    if hProcess:
        pageStart = 0
        while True:
            information = virtual_query_ex(hProcess, pageStart)
            if information == 0:
                break
            # 0x10000 is MEM_FREE
            if information[5] != 0x10000:
                memory_map[pid].add(copy.deepcopy(information))
            newAddress = information[0] + information[4]
            if newAddress <= pageStart:
                break
            pageStart = newAddress
    return memory_map


def getUserPath():
    return "C:\\Users\\%s\\" % os.getenv("username")


def prepareOperatingSystem(config, userPath):
    if config["hook32"]:
        logging.info("placing hook for 32bit processes")
        place_hook_in_registry(userPath + config["hook32"], "SOFTWARE\\Wow6432Node\\Microsoft\\Windows NT\\CurrentVersion\\Windows")
    if config["hook64"]:
        logging.info("placing hook for 64bit processes")
        place_hook_in_registry(userPath + config["hook64"], "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Windows")


def startAsLibrary(samplePath):
    logging.info("launching as DLL")
    try:
        pe = pefile.PE(samplePath)
        rundll_path = os.sep.join(["C:", "Windows", "SysWOW64", "rundll32.exe"])
        if pe.PE_TYPE == 0x20b:
            rundll_path = os.sep.join(["C:", "Windows", "System32", "rundll32.exe"])
        logging.info("using rundll path: {}".format(rundll_path))
        logging.info("Starting DllMain...".format(rundll_path))
        launchProcess("{} {},{}".format(rundll_path, samplePath, "DllMain"))
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            logging.info("Starting function name {} and ordinal {}".format(exp.name, exp.ordinal))
            func = exp.name if exp.name else exp.ordinal
            launchProcess("{} {},{}".format(rundll_path, samplePath, str(func)))
    except:
        logging.error("failed launching as DLL.")


def startAsExe(config, userInteractor, samplePath, sampleName):
    if config["spoof_user"]:
        logging.info("start sample with a double click.")
        userInteractor.launch_sample(config["desktop_sample_pos_x"], config["desktop_sample_pos_x"])
    else:
        logging.info("starting sample via kernel32.CreateProcess()")
        try:
            launchProcess(samplePath + sampleName)
        except:
            logging.error("failed starting with kernel32.CreateProcess().")
