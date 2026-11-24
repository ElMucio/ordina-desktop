"""Icona vicino all'orologio e scorciatoia globale, in un thread con il suo ciclo di messaggi.

Gli eventi arrivano all'interfaccia tramite una coda: Tk va toccato solo dal suo thread.
"""
import ctypes
import threading
from ctypes import POINTER, WINFUNCTYPE, byref, c_ssize_t, wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WINDOW_CLASS = "OrdinaDesktopTray"
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000
WM_HOTKEY = 0x0312
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_SHOW_REQUEST = WM_APP + 2
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
SM_CXSMICON = 49
MF_STRING, MF_SEPARATOR = 0, 0x800
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x100, 0x2
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 1, 2, 0x4000
HOTKEY_ID = 1

CMD_RESTORE, CMD_OPEN, CMD_QUIT = 1, 2, 3

WNDPROC = WINFUNCTYPE(c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_ubyte * 16), ("hBalloonIcon", wintypes.HICON)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = c_ssize_t
user32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetCursorPos.argtypes = [POINTER(wintypes.POINT)]
user32.GetMessageW.argtypes = [POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [POINTER(wintypes.MSG)]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

ERROR_ALREADY_EXISTS = 183
_instance_mutex = None


def claim_single_instance():
    """False se l'app è già aperta: in quel caso le chiede di mostrare la finestra."""
    global _instance_mutex
    _instance_mutex = kernel32.CreateMutexW(None, False, "Local\\OrdinaDesktop")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def ask_running_instance_to_show():
    hwnd = user32.FindWindowW(WINDOW_CLASS, None)
    if hwnd:
        user32.PostMessageW(hwnd, WM_SHOW_REQUEST, 0, 0)


class Tray(threading.Thread):
    def __init__(self, icon_path, tooltip, events):
        super().__init__(daemon=True)
        self.icon_path = str(icon_path)
        self.tooltip = tooltip
        self.events = events
        self.hwnd = None
        self.hotkey_ok = False
        self.ready = threading.Event()
        self._wndproc = WNDPROC(self._on_message)  # riferimento da tenere: Windows lo richiama

    def run(self):
        instance = kernel32.GetModuleHandleW(None)
        window_class = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=instance, lpszClassName=WINDOW_CLASS)
        user32.RegisterClassW(byref(window_class))
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        # Finestra vera ma invisibile: quelle "message-only" non ricevono TaskbarCreated.
        self.hwnd = user32.CreateWindowExW(0, WINDOW_CLASS, "Ordina Desktop", 0, 0, 0, 0, 0, None, None, instance, None)
        size = user32.GetSystemMetrics(SM_CXSMICON)
        self._icon = user32.LoadImageW(None, self.icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE)
        self._add_icon()
        self.hotkey_ok = bool(user32.RegisterHotKey(self.hwnd, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("R")))
        self.ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

    def stop(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            self.join(2)

    def _data(self, flags=0):
        data = NOTIFYICONDATAW(uFlags=flags, hWnd=self.hwnd, uID=1)
        data.cbSize = ctypes.sizeof(data)
        return data

    def _add_icon(self):
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._icon
        data.szTip = self.tooltip
        shell32.Shell_NotifyIconW(NIM_ADD, byref(data))

    def notify(self, title, text):
        data = self._data(NIF_INFO)
        data.szInfoTitle = title[:63]
        data.szInfo = text[:255]
        shell32.Shell_NotifyIconW(NIM_MODIFY, byref(data))

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, CMD_RESTORE, "Ripristina icone\tCtrl+Alt+R")
        user32.AppendMenuW(menu, MF_STRING, CMD_OPEN, "Apri Ordina Desktop")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "Esci")
        user32.SetMenuDefaultItem(menu, CMD_RESTORE, 0)
        point = wintypes.POINT()
        user32.GetCursorPos(byref(point))
        user32.SetForegroundWindow(self.hwnd)  # altrimenti il menu non si chiude cliccando fuori
        choice = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, point.x, point.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        event = {CMD_RESTORE: "restore", CMD_OPEN: "open", CMD_QUIT: "quit"}.get(choice)
        if event:
            self.events.put(event)

    def _on_message(self, hwnd, message, wparam, lparam):
        if message == WM_TRAY:
            if lparam == WM_LBUTTONUP:
                self.events.put("open")
            elif lparam == WM_RBUTTONUP:
                self._show_menu()
            return 0
        if message == WM_HOTKEY:
            self.events.put("restore")
            return 0
        if message == WM_SHOW_REQUEST:
            self.events.put("open")
            return 0
        if message == self._taskbar_created:  # Explorer riavviato: l'icona va rimessa
            self._add_icon()
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            user32.UnregisterHotKey(hwnd, HOTKEY_ID)
            shell32.Shell_NotifyIconW(NIM_DELETE, byref(self._data()))
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)
