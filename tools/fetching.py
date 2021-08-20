import os
import shutil
import tarfile
import tempfile
import zipfile
import traceback
import requests
import apkutils2
from logzero import logger
from adbutils import device as get_device

device = get_device()
atx_agent_version = "0.10.0"

__all__ = ["get_atx_agent_bundle", "get_whatsinput_apk"]


def get_atx_agent_bundle() -> str:
    """
    bundle all platform atx-agent binary into one zip file
    """
    version = atx_agent_version
    target_zip = f"vendor/atx-agent-{version}.zip"
    if not os.path.isfile(target_zip):
        os.makedirs("vendor", exist_ok=True)
        create_atx_agent_bundle(version, target_zip)
    return target_zip


def get_whatsinput_apk() -> str:
    target_path = "vendor/WhatsInput-1.0.apk"
    mirror_download(
        "https://github.com/openatx/atxserver2-android-provider/releases/download/v0.2.0/WhatsInput_v1.0.apk",
        target_path,
    )
    return target_path


def get_stf_binaries() -> str:
    """
    Download from https://github.com/openatx/stf-binaries

    Tag 0.2, support to Android P
    Tag 0.3.0 use stf/@devicefarmer
    """
    version = "0.3.0"
    target_path = f"vendor/stf-binaries-{version}.zip"
    mirror_download(
        f"https://github.com/openatx/stf-binaries/archive/{version}.zip", target_path
    )
    return target_path


def get_all():
    get_atx_agent_bundle()
    get_whatsinput_apk()
    get_stf_binaries()


def create_atx_agent_bundle(version: str, target_zip: str):
    print(">>> Bundle atx-agent verison:", version)
    if not target_zip:
        target_zip = f"atx-agent-{version}.zip"

    def binary_url(version: str, arch: str) -> str:
        return "https://github.com/openatx/atx-agent/releases/download/{0}/atx-agent_{0}_linux_{1}.tar.gz".format(
            version, arch
        )

    with tempfile.TemporaryDirectory(prefix="tmp-") as tmpdir:
        tmp_target_zip = target_zip + ".part"

        with zipfile.ZipFile(
            tmp_target_zip, "w", compression=zipfile.ZIP_DEFLATED
        ) as z:
            z.writestr(version, "")

            for arch in ("386", "amd64", "armv6", "armv7"):
                storepath = tmpdir + "/atx-agent-%s.tar.gz" % arch
                url = binary_url(version, arch)
                mirror_download(url, storepath)

                with tarfile.open(storepath, "r:gz") as t:
                    t.extract("atx-agent", path=tmpdir + "/" + arch)
                    z.write("/".join([tmpdir, arch, "atx-agent"]), "atx-agent-" + arch)
        shutil.move(tmp_target_zip, target_zip)
        print(">>> Zip created", target_zip)


def mirror_download(url: str, target: str) -> str:
    logger.info(url)
    """
    Returns:
        target path
    """
    if os.path.exists(target):
        return target
    github_host = "https://github.com"
    if url.startswith(github_host):
        mirror_url = (
            "https://github.com.cnpmjs.org" + url[len(github_host) :]
        )  # mirror of github
        try:
            return download(mirror_url, target)
        except (requests.RequestException, ValueError) as e:
            logger.debug("download from mirror error, use origin source")

    return download(url, target)


def download(url: str, storepath: str):
    target_dir = os.path.dirname(storepath) or "."
    os.makedirs(target_dir, exist_ok=True)

    r = requests.get(url, stream=True)
    r.raise_for_status()
    total_size = int(r.headers.get("Content-Length", "-1"))
    bytes_so_far = 0
    prefix = "Downloading %s" % os.path.basename(storepath)
    chunk_length = 16 * 1024
    with open(storepath + ".part", "wb") as f:
        for buf in r.iter_content(chunk_length):
            bytes_so_far += len(buf)
            print(f"\r{prefix} {bytes_so_far} / {total_size}", end="", flush=True)
            f.write(buf)
        print(" [Done]")
    if total_size != -1 and os.path.getsize(storepath + ".part") != total_size:
        raise ValueError("download size mismatch")
    shutil.move(storepath + ".part", storepath)

def init_binaries():
    # minitouch, minicap, minicap.so
    d = device
    sdk = d.getprop("ro.build.version.sdk")  # eg 26
    abi = d.getprop("ro.product.cpu.abi")  # eg arm64-v8a
    abis = (d.getprop("ro.product.cpu.abilist").strip() or abi).split(",")
    # pre = d.getprop('ro.build.version.preview_sdk')  # eg 0
    # if pre and pre != "0":
    #    sdk = sdk + pre

    logger.debug("sdk: %s, abi: %s, abis: %s", sdk, abi, abis)

    stf_zippath = get_stf_binaries()
    zip_folder, _ = os.path.splitext(os.path.basename(stf_zippath))
    prefix = zip_folder + "/node_modules/@devicefarmer/minicap-prebuilt/prebuilt/"
    push_stf(
        prefix + abi + "/lib/android-" + sdk + "/minicap.so",
        "/data/local/tmp/minicap.so",
        mode=0o644,
        zipfile_path=stf_zippath,
    )
    push_stf(
        prefix + abi + "/bin/minicap",
        "/data/local/tmp/minicap",
        zipfile_path=stf_zippath,
    )

    prefix = zip_folder + "/node_modules/minitouch-prebuilt/prebuilt/"
    push_stf(
        prefix + abi + "/bin/minitouch",
        "/data/local/tmp/minitouch",
        zipfile_path=stf_zippath,
    )

    # atx-agent
    abimaps = {
        "armeabi-v7a": "atx-agent-armv7",
        "arm64-v8a": "atx-agent-armv7",
        "armeabi": "atx-agent-armv6",
        "x86": "atx-agent-386",
    }
    okfiles = [abimaps[abi] for abi in abis if abi in abimaps]
    logger.debug("use atx-agent: %s", okfiles[0])
    zipfile_path = get_atx_agent_bundle()
    push_stf(okfiles[0], "/data/local/tmp/atx-agent", zipfile_path=zipfile_path)

def push_stf(path: str, dest: str, zipfile_path: str, mode=0o755):
    """push minicap and minitouch from zip"""
    with zipfile.ZipFile(zipfile_path) as z:
        if path not in z.namelist():
            logger.warning("stf stuff %s not found", path)
            return
        src_info = z.getinfo(path)
        dest_info = device.sync.stat(dest)
        if dest_info.size == src_info.file_size and dest_info.mode & mode == mode:
            logger.debug("already pushed %s", path)
            return
        with z.open(path) as f:
            device.sync.push(f, dest, mode)

def init_apks():
    whatsinput_apk_path = get_whatsinput_apk()
    install_apk(whatsinput_apk_path)

def install_apk(path: str):
    assert path, "Invalid %s" % path
    try:
        m = apkutils2.APK(path).manifest
        info = device.package_info(m.package_name)
        if (
            info
            and m.version_code == info["version_code"]
            and m.version_name == info["version_name"]
        ):
            logger.debug("already installed %s", path)
        else:
            logger.debug("install %s", path)
            device.install(path, force=True)
    except Exception as e:
        traceback.print_exc()
        logger.warning("Install apk %s error %s", path, e)
