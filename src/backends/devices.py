"""Pinned ggml device ABI: select measured hardware, never assume GPU index zero."""
import ctypes
import threading

_lock = threading.Lock()
_initialized = False


def probe_devices():
    global _initialized
    from llama_cpp import llama_cpp as c
    with _lock:
        if not _initialized:
            c.llama_backend_init()
            _initialized = True
        lib = c._lib
        lib.ggml_backend_dev_count.restype = ctypes.c_size_t
        lib.ggml_backend_dev_get.argtypes = [ctypes.c_size_t]
        lib.ggml_backend_dev_get.restype = ctypes.c_void_p
        for name in ('ggml_backend_dev_name','ggml_backend_dev_description'):
            function = getattr(lib,name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_char_p
        lib.ggml_backend_dev_type.argtypes = [ctypes.c_void_p]
        lib.ggml_backend_dev_type.restype = ctypes.c_int
        lib.ggml_backend_dev_memory.argtypes = [ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
        lib.ggml_backend_dev_memory.restype = None
        devices=[]
        for index in range(lib.ggml_backend_dev_count()):
            pointer=lib.ggml_backend_dev_get(index)
            if lib.ggml_backend_dev_type(pointer) not in (1,2):
                continue
            free,total=ctypes.c_size_t(),ctypes.c_size_t()
            lib.ggml_backend_dev_memory(pointer,ctypes.byref(free),ctypes.byref(total))
            devices.append({'name':lib.ggml_backend_dev_name(pointer).decode(),
                'description':lib.ggml_backend_dev_description(pointer).decode(),
                'gpu_index':len(devices),'free_bytes':free.value,'total_bytes':total.value,
                '_pointer':pointer})
        return devices


def select_device(devices, configured='auto', min_free_gb=0):
    if configured and configured!='auto':
        candidates=[d for d in devices if d['description']==configured]
        if len(candidates)!=1:
            raise ValueError('الجهاز المحفوظ غير موجود أو اسمه ملتبس؛ راجع إعدادات GPU.')
    else:
        candidates=sorted(devices,key=lambda d:(d['total_bytes'],d['free_bytes']),reverse=True)
    candidates=[d for d in candidates if d['free_bytes']>=min_free_gb*1e9]
    if not candidates:
        raise ValueError('لا توجد ذاكرة GPU متاحة تكفي التقدير. أغلق الأحمال الأخرى أو اختر CPU صراحةً.')
    return candidates[0]
