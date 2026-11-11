"""Request timeouts: a server that accepts connections but never answers must not hang the client."""

import asyncio
import socket
import threading
import time
import unittest
from unittest import mock

from tusclient import client
from tusclient.exceptions import TusCommunicationError, TusUploadFailed

FILEPATH_TEXT = "tests/sample_files/text.txt"


class StalledServer:
    """Accepts TCP connections, reads whatever arrives, and never responds."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.url = "http://127.0.0.1:{}/files/".format(self.sock.getsockname()[1])
        self.connections = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections.append(conn)

    def close(self):
        for conn in self.connections:
            conn.close()
        self.sock.close()


class TimeoutTest(unittest.TestCase):
    def setUp(self):
        self.server = StalledServer()
        self.client = client.TusClient(self.server.url, timeout=0.5)

    def tearDown(self):
        self.server.close()

    def assertFast(self, started):
        self.assertLess(time.monotonic() - started, 5)

    def test_default_is_no_timeout(self):
        self.assertIsNone(client.TusClient("http://example.com/files/").timeout)

    def test_create_url_times_out(self):
        uploader = self.client.uploader(FILEPATH_TEXT)
        started = time.monotonic()
        with self.assertRaises(TusCommunicationError):
            uploader.create_url()
        self.assertFast(started)

    def test_get_offset_times_out(self):
        with mock.patch("tusclient.uploader.baseuploader.BaseUploader.get_offset", return_value=0):
            uploader = self.client.uploader(FILEPATH_TEXT, url=self.server.url + "abc")
        started = time.monotonic()
        with self.assertRaises(TusCommunicationError):
            uploader.get_offset()
        self.assertFast(started)

    def test_upload_chunk_times_out(self):
        with mock.patch("tusclient.uploader.baseuploader.BaseUploader.get_offset", return_value=0):
            uploader = self.client.uploader(FILEPATH_TEXT, url=self.server.url + "abc")
        started = time.monotonic()
        with self.assertRaises(TusUploadFailed):
            uploader.upload_chunk()
        self.assertFast(started)

    def test_tuple_timeout_is_passed_to_requests(self):
        tuple_client = client.TusClient(self.server.url, timeout=(3, 7))
        with mock.patch("tusclient.uploader.baseuploader.BaseUploader.get_offset", return_value=0):
            uploader = tuple_client.uploader(FILEPATH_TEXT, url=self.server.url + "abc")
        with mock.patch("tusclient.request.requests.patch") as patch:
            patch.return_value.headers = {"upload-offset": "11"}
            patch.return_value.status_code = 204
            uploader.upload_chunk()
        self.assertEqual(patch.call_args.kwargs["timeout"], (3, 7))

    def test_async_create_url_times_out(self):
        uploader = self.client.async_uploader(FILEPATH_TEXT)
        started = time.monotonic()
        with self.assertRaises(TusCommunicationError):
            asyncio.run(uploader.create_url())
        self.assertFast(started)

    def test_async_upload_chunk_times_out(self):
        with mock.patch("tusclient.uploader.baseuploader.BaseUploader.get_offset", return_value=0):
            uploader = self.client.async_uploader(FILEPATH_TEXT, url=self.server.url + "abc")
        started = time.monotonic()
        with self.assertRaises(TusUploadFailed):
            asyncio.run(uploader.upload_chunk())
        self.assertFast(started)
