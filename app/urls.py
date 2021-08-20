import os

from .handlers.handlers import (
    IndexHandler,
    WebSocketForwardHandler,
    HttpForwardHandler,
    UploadListHandler,
    UploadItemHandler,
    InstallHandler,
)


url_patterns = [
    (r"/", IndexHandler),
    (
        r"/minicap",
        WebSocketForwardHandler,
        dict(forward_uri="ws://127.0.0.1:7912/minicap"),
    ),
    (
        r"/minitouch",
        WebSocketForwardHandler,
        dict(forward_uri="ws://127.0.0.1:7912/minitouch"),
    ),
    (r"/term", WebSocketForwardHandler, dict(forward_uri="ws://127.0.0.1:7912/term")),
    (r"/whatsinput", WebSocketForwardHandler, dict(forward_uri="ws://127.0.0.1:6677/whatsinput", binary=False)),
    (r"/shell", HttpForwardHandler, dict(forward_uri="http://127.0.0.1:7912")),
    (r"/packages/.*", HttpForwardHandler, dict(forward_uri="http://127.0.0.1:7912")),
    (r"/screenshot/.*", HttpForwardHandler, dict(forward_uri="http://127.0.0.1:7912")),
    (r"/info/.*", HttpForwardHandler, dict(forward_uri="http://127.0.0.1:7912")),
    (r"/uploads", UploadListHandler),
    (
        r"/uploads/(.*)",
        UploadItemHandler,
        {"path": os.path.join(os.getcwd(), "uploads")},
    ),
    (r"/install", InstallHandler),
]
