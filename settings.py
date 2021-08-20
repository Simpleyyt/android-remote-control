import logging
import tornado
from tornado.options import define, options


define("port", default=3500, help="run on the given port", type=int)
define("config", default=None, help="tornado config file")
define("debug", default=False, help="debug mode")
tornado.options.parse_command_line()

settings = {}
settings["debug"] = options.debug
settings["template_path"] = "app/templates"
settings["static_path"] = "app/static"

if options.config:
    tornado.options.parse_config_file(options.config)
