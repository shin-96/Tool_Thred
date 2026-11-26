"""Windows DPAPI: secrets can only be decrypted by the current Windows user."""
import base64
import ctypes
from ctypes import wintypes
import os


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]


def _crypt(value,encrypt):
    if os.name!='nt':raise RuntimeError('Lưu token yêu cầu Windows DPAPI.')
    buf=ctypes.create_string_buffer(value);source=Blob(len(value),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte)));target=Blob()
    if encrypt:ok=ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source),'Threads Studio Pro',None,None,None,1,ctypes.byref(target))
    else:ok=ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target))
    if not ok:raise RuntimeError('Không đọc/ghi được token được bảo vệ của Windows.')
    try:return ctypes.string_at(target.data,target.size)
    finally:ctypes.windll.kernel32.LocalFree(target.data)


def protect(text):return base64.b64encode(_crypt(text.encode(),True)).decode()
def unprotect(text):return _crypt(base64.b64decode(text),False).decode()
