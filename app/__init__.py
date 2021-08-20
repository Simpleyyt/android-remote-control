#!/usr/bin/env python

import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.options import options
from tornado.ioloop import IOLoop
from settings import settings
from .urls import url_patterns
from .device import AndroidDevice
from logzero import logger


class AndroidRemoteControlApplication(tornado.web.Application):
    def __init__(self):
        tornado.web.Application.__init__(self, url_patterns, **settings)

def main():
    app = AndroidRemoteControlApplication()
    app.device = AndroidDevice()
    app.device.init()
    app.listen(options.port)
    IOLoop.current().start()
