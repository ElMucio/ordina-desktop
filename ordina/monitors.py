"""Elenco dei monitor collegati, con un identificativo che non dipende dal primario."""
import ctypes
from ctypes import wintypes

from .planner import Monitor, Rect, hardware_of

user32 = ctypes.WinDLL("user32", use_last_error=True)

MONITORINFOF_PRIMARY = 1
EDD_GET_DEVICE_INTERFACE_NAME = 1
DISPLAY_DEVICE_ACTIVE = 1
DPI_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), MonitorEnumProc, wintypes.LPARAM]
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p


class physical_pixels:
    """Con monitor a scale diverse Windows falsa le coordinate alle app non per-monitor:
    dentro questo blocco il thread legge sempre i pixel reali."""

    def __enter__(self):
        self.previous = user32.SetThreadDpiAwarenessContext(DPI_PER_MONITOR_AWARE_V2)
        return self

    def __exit__(self, *exc):
        if self.previous:
            user32.SetThreadDpiAwarenessContext(self.previous)
        return False


def _rect(r):
    return Rect(r.left, r.top, r.right, r.bottom)


def _device_path(device_name):
    index = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(dd)
        if not user32.EnumDisplayDevicesW(device_name, index, ctypes.byref(dd), EDD_GET_DEVICE_INTERFACE_NAME):
            return device_name
        if dd.StateFlags & DISPLAY_DEVICE_ACTIVE and dd.DeviceID:
            return dd.DeviceID
        index += 1


def current_monitors():
    found = []

    def on_monitor(handle, _hdc, _rc, _data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            path = _device_path(info.szDevice)
            found.append(Monitor(
                id=path,
                hardware=hardware_of(path),
                device=info.szDevice,
                bounds=_rect(info.rcMonitor),
                work=_rect(info.rcWork),
                primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
            ))
        return True

    with physical_pixels():
        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(on_monitor), 0)
    return found
