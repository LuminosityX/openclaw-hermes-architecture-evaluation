"""Linux permission-event gate on one owned inode and one exact opener PID."""
import ctypes
import errno
import os
import struct
import threading
import time


class OwnedOpenGate:
    def __init__(self,path,pid):
        self.path=path.resolve();self.pid=pid;self.events=[];self.entered=threading.Event();self.done=threading.Event()
        self.armed=False;self.held=[];self.lock=threading.Lock();self.deadline=None
        libc=ctypes.CDLL(None,use_errno=True)
        libc.fanotify_init.argtypes=[ctypes.c_uint,ctypes.c_uint];libc.fanotify_init.restype=ctypes.c_int
        libc.fanotify_mark.argtypes=[ctypes.c_int,ctypes.c_uint,ctypes.c_ulonglong,ctypes.c_int,ctypes.c_char_p];libc.fanotify_mark.restype=ctypes.c_int
        self.descriptor=libc.fanotify_init(0x1|0x2|0x4,os.O_RDONLY|os.O_CLOEXEC)
        if self.descriptor<0:raise OSError(ctypes.get_errno(),'Owned fanotify permission gate unavailable')
        if libc.fanotify_mark(self.descriptor,0x1,0x10000,-100,os.fsencode(self.path))<0:
            error=ctypes.get_errno();os.close(self.descriptor);raise OSError(error,'Owned fanotify inode mark failed')
        self.inode=self.path.stat().st_ino
        self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()

    def arm(self):
        with self.lock:self.armed=True;self.deadline=time.monotonic()+8
        self.events.append(dict(kind='owned-inode-gate-armed',pid=self.pid,monotonic_ns=time.monotonic_ns()))

    def answer(self,descriptor):
        os.write(self.descriptor,struct.pack('iI',descriptor,1));os.close(descriptor)

    def release(self):
        with self.lock:self.armed=False;held=self.held;self.held=[]
        for descriptor in held:self.answer(descriptor)
        self.events.append(dict(kind='owned-inode-gate-released',monotonic_ns=time.monotonic_ns()))

    def read(self):
        while not self.done.is_set():
            try:data=os.read(self.descriptor,65536)
            except BlockingIOError:data=b''
            except OSError as error:
                if error.errno==errno.EBADF:return
                raise
            offset=0
            while offset+24<=len(data):
                size,version,_,metadata,mask,descriptor,pid=struct.unpack_from('IBBHQii',data,offset)
                if size<24 or version!=3:raise RuntimeError('Unsupported bounded fanotify metadata')
                offset+=size
                if descriptor<0:continue
                match=pid==self.pid and os.fstat(descriptor).st_ino==self.inode
                with self.lock:
                    held=bool(self.armed and match)
                    if held:self.held.append(descriptor)
                self.events.append(dict(kind='actual-owned-file-open',pid=pid,held=held,permission_event=bool(mask&0x10000),monotonic_ns=time.monotonic_ns()))
                if held:self.entered.set()
                else:self.answer(descriptor)
            if self.armed and self.deadline is not None and time.monotonic()>self.deadline:
                self.events.append(dict(kind='owned-inode-gate-timeout',monotonic_ns=time.monotonic_ns()));self.release()
            self.done.wait(.005)

    def close(self):
        self.release();self.done.set();self.thread.join(timeout=2);os.close(self.descriptor)
