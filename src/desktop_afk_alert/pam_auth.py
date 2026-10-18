"""Password-only PAM conversation, used exclusively in a short-lived root worker."""

import ctypes
import ctypes.util


class PamMessage(ctypes.Structure):
    _fields_ = [("style", ctypes.c_int), ("message", ctypes.c_char_p)]


class PamResponse(ctypes.Structure):
    _fields_ = [("response", ctypes.c_void_p), ("code", ctypes.c_int)]


Conversation = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(PamMessage)),
    ctypes.POINTER(ctypes.POINTER(PamResponse)),
    ctypes.c_void_p,
)


class PamConversation(ctypes.Structure):
    _fields_ = [("callback", Conversation), ("data", ctypes.c_void_p)]


def authenticate(username: str, password: bytes) -> bool:
    if not password or len(password) > 4096 or b"\0" in password:
        return False
    pam = ctypes.CDLL(ctypes.util.find_library("pam") or "libpam.so.0")
    libc = ctypes.CDLL(None)
    libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
    libc.calloc.restype = ctypes.c_void_p
    libc.strdup.argtypes = [ctypes.c_char_p]
    libc.strdup.restype = ctypes.c_void_p
    libc.free.argtypes = [ctypes.c_void_p]
    prompted = False

    @Conversation
    def conversation(count, messages, response, _data):
        nonlocal prompted
        if not 1 <= count <= 32:
            return 19
        address = libc.calloc(count, ctypes.sizeof(PamResponse))
        if not address:
            return 5
        replies = ctypes.cast(address, ctypes.POINTER(PamResponse))
        for index in range(count):
            style = messages[index].contents.style
            if style == 1:
                prompted = True
                value = password
            elif style == 2:
                value = username.encode()
            elif style in (3, 4):
                continue
            else:
                for previous in range(index):
                    if replies[previous].response:
                        libc.free(replies[previous].response)
                libc.free(address)
                return 19
            replies[index].response = libc.strdup(value)
            if not replies[index].response:
                for previous in range(index):
                    if replies[previous].response:
                        libc.free(replies[previous].response)
                libc.free(address)
                return 5
        response[0] = replies
        return 0

    pam.pam_start.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(PamConversation), ctypes.POINTER(ctypes.c_void_p)]
    pam.pam_start.restype = ctypes.c_int
    pam.pam_set_item.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    pam.pam_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_acct_mgmt.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_end.argtypes = [ctypes.c_void_p, ctypes.c_int]
    handle = ctypes.c_void_p()
    config = PamConversation(conversation, None)
    result = pam.pam_start(b"sudo", username.encode(), ctypes.byref(config), ctypes.byref(handle))
    if result != 0:
        return False
    try:
        result = pam.pam_set_item(handle, 8, ctypes.c_char_p(username.encode()))
        if result == 0:
            result = pam.pam_authenticate(handle, 1)
        if result == 0:
            result = pam.pam_acct_mgmt(handle, 0)
        return result == 0 and prompted
    finally:
        pam.pam_end(handle, result)
