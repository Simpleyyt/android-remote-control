import time
from adbutils import adb, device
from logzero import logger

class AndroidDevice(object):
    def __init__(self):
        self._procs = []
        self._device = device()
        self._serial = self._device.serial

    def __repr__(self):
        return "[" + self._serial + "]"

    @property
    def serial(self):
        return self._serial

    def init(self):
        logger.info("Init device: %s", self._serial)
        adb.forward(self._serial, "tcp:7912", "tcp:7912")
        adb.forward(self._serial, "tcp:6677", "tcp:6677")
        adb.shell(self._serial, "/data/local/tmp/atx-agent server --stop")
        adb.shell(self._serial, "/data/local/tmp/atx-agent server --nouia -d")
    
    def install(apk_path: str, launch: bool = False) -> str:
        # 解析apk文件
        apk = adb.APK(apk_path)

        # 提前将重名包卸载
        package_name = apk.manifest.package_name
        pkginfo = device.package_info(package_name)
        if pkginfo:
            logger.debug("uninstall: %s", package_name)
            device.uninstall(package_name)

        # 推送到手机
        dst = "/data/local/tmp/tmp-%d.apk" % int(time.time() * 1000)
        logger.debug("push %s %s", apk_path, dst)
        device.sync.push(apk_path, dst)
        logger.debug("install-remote %s", dst)
        # 调用pm install安装
        device.install_remote(dst)

        # 启动应用
        if launch:
            logger.debug("launch %s", package_name)
            device.app_start(package_name)
        return package_name