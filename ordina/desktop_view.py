"""Lettura e spostamento delle icone tramite l'API ufficiale della shell (IFolderView).

Niente scritture nella memoria di explorer.exe. Le interfacce COM sono chiamate per
posizione nella vtable: i numeri VT_* vengono dalle dichiarazioni in shobjidl.h.
"""
import ctypes
from ctypes import HRESULT, POINTER, WINFUNCTYPE, byref, c_int, c_long, c_uint, c_void_p, wintypes

from .monitors import physical_pixels
from .planner import Item

ole32 = ctypes.WinDLL("ole32")
user32 = ctypes.WinDLL("user32")
shlwapi = ctypes.WinDLL("shlwapi")

CLSCTX_ALL = 0x17
COINIT_APARTMENTTHREADED = 2
SWC_DESKTOP = 8
SWFO_NEEDDISPATCH = 1
VT_I4 = 3
SVGIO_ALLVIEW = 2
SVSI_POSITIONITEM = 0x80
SHGDN_NORMAL = 0
SHGDN_FORPARSING = 0x8000
FWF_AUTOARRANGE = 0x1
FWF_SNAPTOGRID = 0x4

VT_QUERY_INTERFACE = 0
VT_RELEASE = 2
VT_FIND_WINDOW_SW = 15  # IShellWindows
VT_QUERY_SERVICE = 3  # IServiceProvider
VT_QUERY_ACTIVE_SHELL_VIEW = 15  # IShellBrowser
VT_GET_WINDOW = 3  # IShellView
VT_GET_FOLDER = 5  # IFolderView
VT_ITEM = 6
VT_ITEM_COUNT = 7
VT_GET_ITEM_POSITION = 11
VT_GET_SPACING = 12
VT_SELECT_AND_POSITION_ITEMS = 16
VT_SET_CURRENT_FOLDER_FLAGS = 24  # IFolderView2
VT_GET_CURRENT_FOLDER_FLAGS = 25
VT_GET_DISPLAY_NAME_OF = 11  # IShellFolder


class GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ole32.CLSIDFromString(text, byref(self))


class VARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.WORD), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("lVal", c_long), ("pad", ctypes.c_ubyte * 12)]


class STRRET(ctypes.Structure):
    _fields_ = [("uType", c_uint), ("data", ctypes.c_ubyte * 260)]
    _align_ = 8


ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, POINTER(GUID)]
ole32.CLSIDFromString.restype = HRESULT
ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = HRESULT
ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, wintypes.DWORD, POINTER(GUID), POINTER(c_void_p)]
ole32.CoCreateInstance.restype = HRESULT
ole32.CoTaskMemFree.argtypes = [c_void_p]
ole32.CoTaskMemFree.restype = None
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.ClientToScreen.argtypes = [wintypes.HWND, POINTER(wintypes.POINT)]
shlwapi.StrRetToBufW.argtypes = [POINTER(STRRET), c_void_p, wintypes.LPWSTR, c_uint]
shlwapi.StrRetToBufW.restype = HRESULT

CLSID_SHELL_WINDOWS = GUID("{9BA05972-F6A8-11CF-A442-00A0C90A8F39}")
IID_SHELL_WINDOWS = GUID("{85CB6900-4D95-11CF-960C-0080C7F4EE85}")
IID_SERVICE_PROVIDER = GUID("{6D5140C1-7436-11CE-8034-00AA006009FA}")
SID_TOP_LEVEL_BROWSER = GUID("{4C96BE40-915C-11CF-99D3-00AA004AE837}")
IID_SHELL_BROWSER = GUID("{000214E2-0000-0000-C000-000000000046}")
IID_SHELL_VIEW = GUID("{000214E3-0000-0000-C000-000000000046}")
IID_FOLDER_VIEW = GUID("{CDE725B0-CCC9-4519-917E-325D72FAB4CE}")
IID_FOLDER_VIEW_2 = GUID("{1AF3A467-214F-4298-908E-06B03E0B39F9}")
IID_SHELL_FOLDER = GUID("{000214E6-0000-0000-C000-000000000046}")


def init_com():
    """Da chiamare una volta nel thread che userà DesktopView."""
    ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)


def _method(obj, index, *argtypes, restype=HRESULT):
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    prototype = WINFUNCTYPE(restype, c_void_p, *argtypes)
    function = prototype(vtable[index])
    return lambda *args: function(obj, *args)


class DesktopView:
    """Da usare con `with`: tiene aperto il collegamento al desktop e i pixel reali."""

    def __enter__(self):
        self._scope = physical_pixels()
        self._scope.__enter__()
        self._objects = []
        self._pidls = {}
        try:
            self._connect()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        for pidl in self._pidls.values():
            ole32.CoTaskMemFree(pidl)
        for obj in reversed(self._objects):
            _method(obj, VT_RELEASE, restype=c_uint)()
        self._scope.__exit__(None, None, None)
        return False

    def _keep(self, pointer):
        if not pointer.value:
            raise OSError("Il desktop di Windows non ha risposto.")
        self._objects.append(pointer.value)
        return pointer.value

    def _query(self, obj, iid):
        out = c_void_p()
        _method(obj, VT_QUERY_INTERFACE, POINTER(GUID), POINTER(c_void_p))(byref(iid), byref(out))
        return self._keep(out)

    def _connect(self):
        out = c_void_p()
        ole32.CoCreateInstance(byref(CLSID_SHELL_WINDOWS), None, CLSCTX_ALL, byref(IID_SHELL_WINDOWS), byref(out))
        windows = self._keep(out)

        location, root = VARIANT(), VARIANT()
        location.vt = VT_I4
        hwnd, out = c_long(), c_void_p()
        _method(windows, VT_FIND_WINDOW_SW, POINTER(VARIANT), POINTER(VARIANT), c_int, POINTER(c_long), c_int,
                POINTER(c_void_p))(byref(location), byref(root), SWC_DESKTOP, byref(hwnd), SWFO_NEEDDISPATCH, byref(out))
        dispatch = self._keep(out)

        provider = self._query(dispatch, IID_SERVICE_PROVIDER)
        out = c_void_p()
        _method(provider, VT_QUERY_SERVICE, POINTER(GUID), POINTER(GUID), POINTER(c_void_p))(
            byref(SID_TOP_LEVEL_BROWSER), byref(IID_SHELL_BROWSER), byref(out))
        browser = self._keep(out)

        out = c_void_p()
        _method(browser, VT_QUERY_ACTIVE_SHELL_VIEW, POINTER(c_void_p))(byref(out))
        shell_view = self._keep(out)

        self._view = self._query(shell_view, IID_FOLDER_VIEW)
        self._view2 = self._query(shell_view, IID_FOLDER_VIEW_2)

        out = c_void_p()
        _method(self._view, VT_GET_FOLDER, POINTER(GUID), POINTER(c_void_p))(byref(IID_SHELL_FOLDER), byref(out))
        self._folder = self._keep(out)

        view_window = wintypes.HWND()
        _method(shell_view, VT_GET_WINDOW, POINTER(wintypes.HWND))(byref(view_window))
        self._list = user32.FindWindowExW(view_window, None, "SysListView32", None) or view_window.value

    def origin(self):
        """Punto dello schermo a cui sono relative le posizioni delle icone."""
        point = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(self._list, byref(point)):
            raise OSError("Origine del desktop non disponibile.")
        return point.x, point.y

    def cell(self):
        point = wintypes.POINT()
        _method(self._view, VT_GET_SPACING, POINTER(wintypes.POINT))(byref(point))
        return point.x, point.y

    def _flags(self):
        flags = wintypes.DWORD()
        _method(self._view2, VT_GET_CURRENT_FOLDER_FLAGS, POINTER(wintypes.DWORD))(byref(flags))
        return flags.value

    def _set_flag(self, flag, on):
        _method(self._view2, VT_SET_CURRENT_FOLDER_FLAGS, wintypes.DWORD, wintypes.DWORD)(flag, flag if on else 0)

    @property
    def auto_arrange(self):
        return bool(self._flags() & FWF_AUTOARRANGE)

    @auto_arrange.setter
    def auto_arrange(self, on):
        self._set_flag(FWF_AUTOARRANGE, on)

    @property
    def snap_to_grid(self):
        return bool(self._flags() & FWF_SNAPTOGRID)

    @snap_to_grid.setter
    def snap_to_grid(self, on):
        self._set_flag(FWF_SNAPTOGRID, on)

    def _name_of(self, pidl, flags):
        value = STRRET()
        _method(self._folder, VT_GET_DISPLAY_NAME_OF, c_void_p, wintypes.DWORD, POINTER(STRRET))(pidl, flags, byref(value))
        buffer = ctypes.create_unicode_buffer(32768)
        shlwapi.StrRetToBufW(byref(value), pidl, buffer, len(buffer))
        return buffer.value

    def read_items(self):
        for pidl in self._pidls.values():
            ole32.CoTaskMemFree(pidl)
        self._pidls = {}
        count = c_int()
        _method(self._view, VT_ITEM_COUNT, c_uint, POINTER(c_int))(SVGIO_ALLVIEW, byref(count))
        get_item = _method(self._view, VT_ITEM, c_int, POINTER(c_void_p))
        get_position = _method(self._view, VT_GET_ITEM_POSITION, c_void_p, POINTER(wintypes.POINT))
        items = []
        for index in range(count.value):
            pidl = c_void_p()
            get_item(index, byref(pidl))
            point = wintypes.POINT()
            get_position(pidl, byref(point))
            item_id = self._name_of(pidl, SHGDN_FORPARSING)
            self._pidls[item_id] = pidl
            items.append(Item(item_id, self._name_of(pidl, SHGDN_NORMAL), point.x, point.y))
        return items

    def move(self, moves):
        """moves: {id icona: (x, y)}; richiede una read_items() precedente."""
        if not moves:
            return
        count = len(moves)
        pidls = (c_void_p * count)(*(self._pidls[item_id] for item_id in moves))
        points = (wintypes.POINT * count)(*(wintypes.POINT(x, y) for x, y in moves.values()))
        _method(self._view, VT_SELECT_AND_POSITION_ITEMS, c_uint, c_void_p, c_void_p, wintypes.DWORD)(
            count, pidls, points, SVSI_POSITIONITEM)
