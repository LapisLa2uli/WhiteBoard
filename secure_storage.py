"""OS-protected secrets: DPAPI on Windows, Keychain on macOS. No plaintext fallback."""
import ctypes as C
import hashlib
import json
import sys
from pathlib import Path
from persistence import atomic_bytes, remove_json


class SecretStorageError(RuntimeError):
    pass


def _dpapi(payload, decrypt=False):
    from ctypes import wintypes as W
    class Blob(C.Structure):
        _fields_ = [('size', W.DWORD), ('data', C.POINTER(C.c_ubyte))]
    memory = C.create_string_buffer(payload)
    source = Blob(len(payload), C.cast(memory, C.POINTER(C.c_ubyte)))
    result = Blob()
    crypt = C.WinDLL('crypt32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [C.POINTER(Blob), C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, W.DWORD, C.POINTER(Blob)]
    fn.restype = W.BOOL
    if not fn(C.byref(source), None, None, None, None, 1, C.byref(result)):
        raise SecretStorageError('Windows could not unlock the saved credentials. Sign in again.')
    try:
        return C.string_at(result.data, result.size)
    finally:
        free = C.windll.kernel32.LocalFree
        free.argtypes = [C.c_void_p]
        free.restype = C.c_void_p
        free(result.data)


def _keychain(key, payload=None, *, delete=False):
    cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    sec = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
    P = C.c_void_p
    cf.CFStringCreateWithCString.argtypes = [P, C.c_char_p, C.c_uint32]
    cf.CFStringCreateWithCString.restype = P
    cf.CFDataCreate.argtypes = [P, P, C.c_long]
    cf.CFDataCreate.restype = P
    cf.CFDictionaryCreate.argtypes = [P, C.POINTER(P), C.POINTER(P), C.c_long, P, P]
    cf.CFDictionaryCreate.restype = P
    cf.CFDataGetLength.argtypes = [P]
    cf.CFDataGetLength.restype = C.c_long
    cf.CFDataGetBytePtr.argtypes = [P]
    cf.CFDataGetBytePtr.restype = P
    cf.CFRelease.argtypes = [P]
    sec.SecItemCopyMatching.argtypes = [P, C.POINTER(P)]
    sec.SecItemAdd.argtypes = [P, C.POINTER(P)]
    sec.SecItemUpdate.argtypes = [P, P]
    sec.SecItemDelete.argtypes = [P]
    owned = []
    def string(value):
        obj = cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)
        owned.append(obj)
        return obj
    def constant(name):
        return P.in_dll(sec, name).value
    def dictionary(items):
        keys = (P * len(items))(*(constant(k) for k in items))
        vals = (P * len(items))(*items.values())
        obj = cf.CFDictionaryCreate(None, keys, vals, len(items), None, None)
        owned.append(obj)
        return obj
    try:
        query = {'kSecClass': constant('kSecClassGenericPassword'), 'kSecAttrService': string('WhiteBoard'), 'kSecAttrAccount': string(key)}
        if delete:
            status = sec.SecItemDelete(dictionary(query))
        elif payload is not None:
            buf = C.create_string_buffer(payload)
            value = cf.CFDataCreate(None, buf, len(payload))
            owned.append(value)
            status = sec.SecItemUpdate(dictionary(query), dictionary({'kSecValueData': value}))
            if status == -25300:
                query.update(kSecValueData=value, kSecAttrAccessible=constant('kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly'))
                status = sec.SecItemAdd(dictionary(query), None)
        else:
            query['kSecReturnData'] = P.in_dll(cf, 'kCFBooleanTrue').value
            result = P()
            status = sec.SecItemCopyMatching(dictionary(query), C.byref(result))
            if status == -25300:
                return None
            if status == 0:
                owned.append(result.value)
                return C.string_at(cf.CFDataGetBytePtr(result), cf.CFDataGetLength(result))
        if status not in (0, -25300):
            raise SecretStorageError('macOS Keychain is unavailable or locked. Unlock it and try again.')
    finally:
        for obj in reversed(owned):
            cf.CFRelease(obj)


def _key(path):
    return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()


def save_secret(path, value):
    path = Path(path)
    payload = json.dumps(value, separators=(',', ':')).encode()
    if sys.platform == 'win32':
        envelope = b'WBDP1\n' + _dpapi(payload)
    elif sys.platform == 'darwin':
        _keychain(_key(path), payload)
        envelope = b'WBKC1\n'
    else:
        raise SecretStorageError('Secure credential storage is unavailable on this system.')
    atomic_bytes(path, envelope)
    path.with_suffix(path.suffix + '.bak').unlink(missing_ok=True)


def load_secret(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    raw = path.read_bytes()
    if raw.startswith(b'WBDP1\n') and sys.platform == 'win32':
        return json.loads(_dpapi(raw[6:], decrypt=True))
    if raw.startswith(b'WBKC1\n') and sys.platform == 'darwin':
        payload = _keychain(_key(path))
        return json.loads(payload) if payload else default
    # One-time migration of an older plaintext installation; never keep a backup.
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise SecretStorageError('Saved credentials could not be read. Sign in again.') from exc
    save_secret(path, value)
    return value


def delete_secret(path):
    if sys.platform == 'darwin':
        _keychain(_key(path), delete=True)
    remove_json(path)
