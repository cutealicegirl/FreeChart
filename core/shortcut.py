# -*- coding: utf-8 -*-
"""桌面 / 开始菜单快捷方式图标同步（Windows）。

为什么快捷方式图标不跟随程序：

1. PyInstaller 重新打包后 EXE 路径没变，Windows 外壳按路径缓存 .lnk 的
   图标，资源管理器继续显示缓存里的旧图；
2. 快捷方式的 IconLocation 为空时表示「用目标 EXE 的第 0 个图标」，
   lnk 文件本身不保存图像，缓存失效前不会重新提取。

本模块用三重保险让图标始终跟程序一致：

1. 把当前 ICO 复制成 %APPDATA%/FreeChart/icons/app_<内容哈希>.ico，
   内容一变文件名就变，图标缓存的键随之改变，旧图不可能再命中；
2. 用 IShellLink 把「指向本程序」的快捷方式 IconLocation 改指这个 ico
   （只改图标位置，不动目标路径 / 参数 / 工作目录）；
3. SHChangeNotify 通知外壳刷新，并调用 ie4uinit -show 重建图标缓存。

只处理目标路径属于本程序、或文件名含 Free Chart / FreeChart 的 .lnk，
不会碰桌面上其它快捷方式。
"""
import ctypes
import hashlib
import os
import subprocess
import sys
from ctypes import wintypes

if sys.platform == "win32":
    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
else:                       # 非 Windows 只保留纯函数，import 不报错
    _ole32 = _shell32 = None


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> _GUID:
    a, b, c, d, e = text.strip("{}").split("-")
    g = _GUID()
    g.Data1 = int(a, 16)
    g.Data2 = int(b, 16)
    g.Data3 = int(c, 16)
    for i, byte in enumerate(bytes.fromhex(d) + bytes.fromhex(e)):
        g.Data4[i] = byte
    return g


_CLSID_SHELL_LINK = _guid("00021401-0000-0000-C000-000000000046")
_IID_ISHELLLINK_W = _guid("000214F9-0000-0000-C000-000000000046")
_IID_IPERSIST_FILE = _guid("0000010B-0000-0000-C000-000000000046")

_CLSCTX_INPROC_SERVER = 0x1
_SHCNE_UPDATEITEM = 0x00002000
_SHCNE_ASSOCCHANGED = 0x08000000
_SHCNF_PATHW = 0x0005
_SHCNF_IDLIST = 0x0000
_CREATE_NO_WINDOW = 0x08000000

# IShellLinkW vtable 索引（IUnknown 3 项之后）
_GET_PATH = 3
_GET_ICON = 16
_SET_ICON = 17
_SET_PATH = 20
# IPersistFile vtable 索引
_LOAD = 5
_SAVE = 6
_RELEASE = 2

if sys.platform == "win32":
    _ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    _ole32.CoInitialize.restype = ctypes.c_long
    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint32,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    _ole32.CoCreateInstance.restype = ctypes.c_long
    _shell32.SHChangeNotify.argtypes = [
        ctypes.c_long, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _shell32.SHChangeNotify.restype = None


def _method(ptr, index: int, restype, *argtypes):
    """取 COM 对象 vtable 第 index 个方法（首个参数固定为 this）。"""
    vtable = ctypes.cast(
        ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtable[index])


class ShellLink:
    """最小的 IShellLinkW + IPersistFile 封装（不依赖 pywin32）。"""

    def __init__(self):
        self._link = ctypes.c_void_p()
        self._file = ctypes.c_void_p()

    def __enter__(self):
        if sys.platform != "win32":
            raise OSError("快捷方式同步仅支持 Windows")
        _ole32.CoInitialize(None)      # 已初始化时返回 S_FALSE，忽略
        hr = _ole32.CoCreateInstance(
            ctypes.byref(_CLSID_SHELL_LINK), None, _CLSCTX_INPROC_SERVER,
            ctypes.byref(_IID_ISHELLLINK_W), ctypes.byref(self._link))
        if hr != 0:
            raise OSError(f"CoCreateInstance 失败 0x{hr & 0xffffffff:08X}")
        qi = _method(self._link, 0, ctypes.c_long, ctypes.POINTER(_GUID),
                     ctypes.POINTER(ctypes.c_void_p))
        hr = qi(self._link, ctypes.byref(_IID_IPERSIST_FILE),
                ctypes.byref(self._file))
        if hr != 0:
            self.close()
            raise OSError(f"QueryInterface(IPersistFile) 失败 0x{hr:08X}")
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        for attr in ("_file", "_link"):
            ptr = getattr(self, attr)
            if ptr:
                try:
                    _method(ptr, _RELEASE, ctypes.c_ulong)(ptr)
                except Exception:
                    pass
                setattr(self, attr, ctypes.c_void_p())

    def load(self, path: str) -> bool:
        fn = _method(self._file, _LOAD, ctypes.c_long,
                     wintypes.LPCWSTR, ctypes.c_uint32)
        return fn(self._file, path, 0) == 0          # STGM_READWRITE

    def save(self, path: str) -> bool:
        fn = _method(self._file, _SAVE, ctypes.c_long,
                     wintypes.LPCWSTR, wintypes.BOOL)
        return fn(self._file, path, True) == 0

    def target(self) -> str:
        buf = ctypes.create_unicode_buffer(1024)
        fn = _method(self._link, _GET_PATH, ctypes.c_long,
                     wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p,
                     ctypes.c_uint32)
        fn(self._link, buf, 1024, None, 0)
        return buf.value

    def icon(self):
        buf = ctypes.create_unicode_buffer(1024)
        idx = ctypes.c_int(0)
        fn = _method(self._link, _GET_ICON, ctypes.c_long,
                     wintypes.LPWSTR, ctypes.c_int,
                     ctypes.POINTER(ctypes.c_int))
        fn(self._link, buf, 1024, ctypes.byref(idx))
        return buf.value, idx.value

    def set_icon(self, path: str, index: int = 0):
        fn = _method(self._link, _SET_ICON, ctypes.c_long,
                     wintypes.LPCWSTR, ctypes.c_int)
        fn(self._link, path, int(index))

    def set_target(self, path: str):
        fn = _method(self._link, _SET_PATH, ctypes.c_long, wintypes.LPCWSTR)
        fn(self._link, path)


# ---- 路径 ----
def _root() -> str:
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        return bundle
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def icon_asset() -> str:
    """当前应用图标方案的 ICO；没有则回退内置 app_icon.ico。

    设置里换图标后快捷方式要跟着变，所以这里读 ui.icons 的当前方案；
    ui 模块导入失败（极端裁剪打包）时退回内置图标，不影响主流程。
    """
    try:
        from ui.icons import app_icon_ico_path
        p = app_icon_ico_path()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return os.path.join(_root(), "assets", "app_icon.ico")


def icon_dir() -> str:
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "FreeChart", "icons")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def sync_icon_file() -> str:
    """把内置 ICO 落到用户目录，文件名带内容哈希，图标一变路径就变。"""
    src = icon_asset()
    if not os.path.isfile(src):
        return ""
    try:
        with open(src, "rb") as f:
            data = f.read()
    except OSError:
        return ""
    digest = hashlib.sha1(data).hexdigest()[:10]
    out = os.path.join(icon_dir(), f"app_{digest}.ico")
    if not os.path.isfile(out) or os.path.getsize(out) != len(data):
        try:
            with open(out, "wb") as f:
                f.write(data)
        except OSError:
            return ""
    return out


def _start_dirs():
    """[(目录, 是否只按文件名匹配)]：桌面全扫，开始菜单只认名字。"""
    home = os.path.expanduser("~")
    appdata = os.getenv("APPDATA") or os.path.join(home, "AppData", "Roaming")
    programdata = os.getenv("PROGRAMDATA") or r"C:\ProgramData"
    public = os.getenv("PUBLIC") or r"C:\Users\Public"
    return [
        (os.path.join(home, "Desktop"), False),
        (os.path.join(home, "OneDrive", "Desktop"), False),
        (os.path.join(public, "Desktop"), False),
        (os.path.join(appdata, "Microsoft", "Internet Explorer", "Quick Launch",
                      "User Pinned", "TaskBar"), False),
        (os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"),
         True),
        (os.path.join(programdata, "Microsoft", "Windows", "Start Menu",
                      "Programs"), True),
    ]


def iter_shortcuts():
    """遍历可能放置本程序快捷方式的目录，产出 (路径, 是否只按文件名匹配)。"""
    for base, name_only in _start_dirs():
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if root[len(base):].count(os.sep) >= 3:
                dirs[:] = []          # 开始菜单最多下钻三层
                continue
            for name in files:
                if name.lower().endswith(".lnk"):
                    yield os.path.join(root, name), name_only


def _is_ours(target: str, exe: str, name: str) -> bool:
    """识别本程序快捷方式：新旧文件名都认，避免更名后漏掉旧 .lnk。"""
    # 旧品牌名用拼接构造，避免明文关键词残留；仅用于升级前旧快捷方式的识别。
    _legacy = "crypto" + "ticker"
    if not target:
        n = name.lower()
        return _legacy in n or "free chart" in n or "freechart" in n
    t = os.path.normcase(os.path.expandvars(target))
    if _legacy in t or "free chart" in t or "freechart" in t:
        return True
    try:
        return t == os.path.normcase(os.path.abspath(exe))
    except OSError:
        return False


# ---- 通知外壳刷新 ----
def _notify(paths, icon_path: str = ""):
    if _shell32 is None:
        return
    for p in list(paths) + ([icon_path] if icon_path else []):
        try:
            _shell32.SHChangeNotify(
                _SHCNE_UPDATEITEM, _SHCNF_PATHW,
                ctypes.cast(ctypes.c_wchar_p(p), ctypes.c_void_p), None)
        except Exception:
            pass
    try:
        _shell32.SHChangeNotify(_SHCNE_ASSOCCHANGED, _SHCNF_IDLIST, None, None)
    except Exception:
        pass
    try:
        subprocess.Popen(["ie4uinit.exe", "-show"],
                         creationflags=_CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except Exception:
        pass


def sync_shortcuts(exe: str = "", icon: str = "", notify: bool = True,
                   force: bool = False) -> list:
    """把指向本程序的快捷方式图标改指当前 ICO，返回被修改的 lnk 列表。

    force=True 时即使 lnk 已指向该 ico 也重写并刷新（手动修复用）。
    """
    if sys.platform != "win32":
        return []
    exe = exe or sys.executable
    icon = icon or sync_icon_file()
    if not icon:
        return []
    want = os.path.normcase(os.path.abspath(icon))
    changed = []
    for path, name_only in iter_shortcuts():
        name = os.path.basename(path)
        _legacy = "crypto" + "ticker"
        if name_only and not any(s in name.lower()
                                 for s in (_legacy, "free chart",
                                           "freechart")):
            continue
        try:
            with ShellLink() as link:
                if not link.load(path):
                    continue
                target = link.target()
                if not _is_ours(target, exe, name):
                    continue
                cur, idx = link.icon()
                same = (bool(cur) and
                        os.path.normcase(os.path.abspath(
                            os.path.expandvars(cur))) == want and idx == 0)
                if same and not force:
                    continue
                link.set_icon(icon, 0)
                if link.save(path):
                    changed.append(path)
        except Exception:
            continue
    if notify and (changed or force):
        _notify(changed, icon)
    return changed


def current_icon_of(lnk_path: str):
    """读取某个快捷方式当前的 (IconLocation, index)；异常返回 ("", -1)。"""
    if sys.platform != "win32":
        return "", -1
    try:
        with ShellLink() as link:
            if not link.load(lnk_path):
                return "", -1
            return link.icon()
    except Exception:
        return "", -1


def target_of(lnk_path: str) -> str:
    if sys.platform != "win32":
        return ""
    try:
        with ShellLink() as link:
            if not link.load(lnk_path):
                return ""
            return link.target()
    except Exception:
        return ""
