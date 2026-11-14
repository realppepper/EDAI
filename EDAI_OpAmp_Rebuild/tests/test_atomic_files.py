import ctypes
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from opamp_pipeline.loop_02_handoff import write_json


def sharing_error():
    error = PermissionError('injected Windows sharing lock')
    error.winerror = 5
    return error


class AtomicFilesTests(unittest.TestCase):
    def test_transient_lock_retries_without_rewriting_the_payload(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';write_json(path,{'old':True})
            native=os.replace;calls=[]
            def replace(source,target):
                calls.append(str(source))
                if len(calls)<3:
                    self.assertEqual(json.loads(path.read_text()),{'old':True})
                    raise sharing_error()
                native(source,target)
            with patch('opamp_pipeline.support.atomic_files.os.replace',side_effect=replace),patch('opamp_pipeline.support.atomic_files.time.sleep'):
                write_json(path,{'new':'complete'})
            self.assertEqual(len(calls),3)
            self.assertEqual(len(set(calls)),1)
            self.assertEqual(json.loads(path.read_text()),{'new':'complete'})
            self.assertFalse(list(Path(d).glob('*.tmp')))

    def test_persistent_lock_is_bounded_and_preserves_old_state_and_staging(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';write_json(path,{'old':True})
            with patch('opamp_pipeline.support.atomic_files.os.replace',side_effect=sharing_error()) as publish,patch('opamp_pipeline.support.atomic_files.time.sleep'):
                with self.assertRaises(PermissionError):write_json(path,{'new':True})
            self.assertEqual(publish.call_count,8)
            self.assertEqual(json.loads(path.read_text()),{'old':True})
            staged=list(Path(d).glob('*.tmp'))
            self.assertEqual(len(staged),1)
            self.assertEqual(json.loads(staged[0].read_text()),{'new':True})

    def test_non_sharing_io_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('opamp_pipeline.support.atomic_files.os.replace',side_effect=OSError('disk unavailable')) as publish:
                with self.assertRaises(OSError):write_json(Path(d)/'state.json',{})
            self.assertEqual(publish.call_count,1)

    def test_invalid_json_does_not_touch_last_good_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';write_json(path,{'old':True})
            with self.assertRaises(ValueError):write_json(path,{'bad':float('nan')})
            self.assertEqual(json.loads(path.read_text()),{'old':True})
            self.assertFalse(list(Path(d).glob('*.tmp')))

    def test_staging_names_are_private_to_each_write(self):
        with tempfile.TemporaryDirectory() as d:
            seen=[];native=os.replace
            def replace(source,target):seen.append(str(source));native(source,target)
            with patch('opamp_pipeline.support.atomic_files.os.replace',side_effect=replace):
                for n in range(3):write_json(Path(d)/'state.json',{'n':n})
            self.assertEqual(len(set(seen)),3)

    @unittest.skipUnless(os.name=='nt','Requires a native Windows sharing lock')
    def test_real_windows_reader_handle_temporarily_blocks_replace(self):
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        api.CreateFileW.restype=wintypes.HANDLE
        api.CloseHandle.argtypes=[wintypes.HANDLE]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';write_json(path,{'old':True})
            handle=api.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            released=threading.Event()
            def release():
                time.sleep(.2);api.CloseHandle(handle);released.set()
            thread=threading.Thread(target=release);thread.start()
            try:write_json(path,{'new':'x'*1000})
            finally:thread.join()
            self.assertTrue(released.is_set())
            self.assertEqual(json.loads(path.read_text()),{'new':'x'*1000})
