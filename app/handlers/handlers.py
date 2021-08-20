import os
import hashlib
import requests
import shutil
import glob
from tornado.web import RequestHandler, stream_request_body, StaticFileHandler
from tornado.websocket import WebSocketHandler
import tornado.httpclient
from tornado.ioloop import IOLoop
from .multipart_streamer import MultiPartStreamer
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor
from logzero import logger


class IndexHandler(RequestHandler):
    async def get(self):
        self.render("index.html")


class WebSocketForwardHandler(WebSocketHandler):
    def initialize(self, forward_uri, binary=True):
        self.forward_uri = forward_uri
        self.binary = binary

    def check_origin(self, origin):
        return True

    async def forward(self):
        while True:
            msg = await self.ws.read_message()
            if msg is None:
                break
            await self.write_message(msg, binary=self.binary)

    async def open(self):
        self.ws = await tornado.websocket.websocket_connect(self.forward_uri)
        IOLoop.current().spawn_callback(self.forward)

    async def on_message(self, msg):
        await self.ws.write_message(msg, binary=self.binary)

    def on_close(self):
        pass


class HttpForwardHandler(RequestHandler):
    def initialize(self, forward_uri):
        self.forward_uri = forward_uri
        self.http_client = tornado.httpclient.AsyncHTTPClient()

    async def get(self):
        response = await self.http_client.fetch(
            self.forward_uri + self.request.uri, headers=self.request.headers
        )
        self.set_status(response.code)
        self._headers = response.headers
        self._headers.pop("Transfer-Encoding", None)
        self.write(response.body)

    async def post(self):
        response = await self.http_client.fetch(
            self.forward_uri + self.request.uri,
            method="POST",
            body=self.request.body,
            headers=self.request.headers,
        )
        self.set_status(response.code)
        self._headers = response.headers
        self._headers.pop("Transfer-Encoding", None)
        self.write(response.body)


@stream_request_body
class UploadListHandler(RequestHandler):  # replace UploadListHandler
    async def prepare(self):
        if self.request.method.lower() == "post":
            self.request.connection.set_max_body_size(8 << 30)  # 8G
        try:
            total = int(self.request.headers.get("Content-Length", "0"))
        except KeyError:
            total = 0
        self.ps = MultiPartStreamer(total)

    def data_received(self, chunk):
        self.ps.data_received(chunk)

    async def post(self):
        try:
            self.ps.data_complete()  # close the incoming stream.
            parts = self.ps.get_parts_by_name("file")
            if len(parts) == 0:
                self.write(
                    {
                        "success": False,
                        "description": 'no form "file" providered',
                    }
                )
                return

            filepart = parts[0]
            filepart.f_out.seek(0)

            # save file
            target_dir = os.path.join(
                "uploads", filepart.md5sum[:2], filepart.md5sum[2:]
            )
            os.makedirs(target_dir, exist_ok=True)
            _, ext = os.path.splitext(filepart.get_filename())
            target_path = os.path.join(target_dir, "file" + ext)
            if not os.path.isfile(target_path):
                filepart.move(target_path)

            # gen file info
            url = "".join(
                [
                    self.request.protocol,
                    "://",
                    self.request.host,
                    "/",
                    target_path.replace("\\", "/"),
                ]
            )
            data = dict(url=url, md5sum=filepart.md5sum)
            self.write(
                {
                    "success": True,
                    "data": data,
                }
            )
        finally:
            self.ps.release_parts()


class InstallHandler(RequestHandler):
    _install_executor = ThreadPoolExecutor(4)
    _download_executor = ThreadPoolExecutor(1)

    def cache_filepath(self, text: str) -> str:
        m = hashlib.md5()
        m.update(text.encode("utf-8"))
        return "cache-" + m.hexdigest()

    @run_on_executor(executor="_download_executor")
    def cache_download(self, url: str) -> str:
        """download with local cache"""
        target_path = self.cache_filepath(url)
        logger.debug("Download %s to %s", url, target_path)

        if os.path.exists(target_path):
            logger.debug("Cache hited")
            return target_path

        # TODO: remove last
        for fname in glob.glob("cache-*"):
            logger.debug("Remove old cache: %s", fname)
            os.unlink(fname)

        tmp_path = target_path + ".tmp"
        r = requests.get(url, stream=True)
        r.raise_for_status()

        with open(tmp_path, "wb") as tfile:
            content_length = int(r.headers.get("content-length", 0))
            if content_length:
                for chunk in r.iter_content(chunk_size=40960):
                    tfile.write(chunk)
            else:
                shutil.copyfileobj(r.raw, tfile)

        os.rename(tmp_path, target_path)
        return target_path

    @run_on_executor(executor="_install_executor")
    def app_install_url(self, apk_path: str, **kwargs):
        return self.application.device.install(apk_path, **kwargs) 

    async def post(self):
        url = self.get_argument("url")
        launch = self.get_argument("launch", "false") in ["true", "True", "TRUE", "1"]

        apk_path = await self.cache_download(url)
        pkg_name = await self.app_install_url(apk_path, launch=launch)
        self.write({
            "success": True,
            "description": "Success",
            "packageName": pkg_name,
        })


class UploadItemHandler(StaticFileHandler):
    async def get(self, path, include_body=True):
        filepath = self.get_absolute_path(self.root, path)
        if os.path.isfile(filepath):
            os.utime(filepath, None)  # update modtime
        await super().get(path, include_body)
