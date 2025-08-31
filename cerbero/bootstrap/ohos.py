
# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2025 Jani Hautakangas <jani@kodegood.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.


# cerbero - a multi-platform build system for Open Source software
# OpenHarmony SDK bootstrapper with safe inner component extraction
# and SDK_VERSION used in the URL.


# cerbero - a multi-platform build system for Open Source software
# OpenHarmony SDK bootstrapper (recursive archive discovery + safe extraction)

import os
import shutil
import glob
import tarfile
import zipfile
import json

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_toolchain_bootstrapper
from cerbero.config import Distro

SDK_VERSION = "6.0"  # used in URL path and marker file
SDK_BASE_URL = "https://repo.huaweicloud.com/openharmony/os/%s-Release/%s"

# TODO: 6.0 mac sdk is not yet available
SDK_CHECKSUMS = {
    "ohos-sdk-windows_linux-public.tar.gz": "a315834ac133625efc912bd078f3e2b2550868d04aef1b5aa4f9679c8b3c9d8e",
    "ohos-sdk-mac-public.tar.gz": "e4dea057e8f57a567ae8e6d45a3a20cafa10bc774c1e5f13ad6f154baaa6985c",
}

WANTED_COMPONENTS = ("native", "toolchains", "ets", "js", "previewer")

def _filename_for_platform(platform: str) -> str:
    return "ohos-sdk-mac-public.tar.gz" if platform == "darwin" else "ohos-sdk-windows_linux-public.tar.gz"

def _platform_dir_name(platform: str) -> str:
    return {"linux": "linux", "windows": "windows", "darwin": "mac"}.get(platform, platform)

def _extract_archive(archive_path: str, dest_dir: str) -> bool:
    os.makedirs(dest_dir, exist_ok=True)
    # normalize extension checks (lowercase)
    low = archive_path.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(dest_dir)
        return True
    if low.endswith(".tar.gz") or low.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(dest_dir)
        return True
    return False

def _read_api_version(component_root: str) -> str | None:
    # Try root-level oh-uni-package.json
    pkg = os.path.join(component_root, "oh-uni-package.json")
    if not os.path.isfile(pkg):
        # Try one level deeper
        candidates = glob.glob(os.path.join(component_root, "*", "oh-uni-package.json"))
        if not candidates:
            return None
        pkg = candidates[0]
    try:
        with open(pkg, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("apiVersion")
        return str(v) if v is not None else None
    except Exception:
        return None

def _find_archives_recursively(root: str) -> list[str]:
    """Find archives recursively under root."""
    patterns = ["**/*.zip", "**/*.tar.gz", "**/*.tgz"]
    found = []
    for pat in patterns:
        found.extend(glob.glob(os.path.join(root, pat), recursive=True))
    return found


class OpenHarmonyBootstrapper(BootstrapperBase):
    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline, 'ohos')
        self.prefix = self.config.toolchain_prefix  # should point to .../ohos-sdk

        fname = _filename_for_platform(self.config.platform)
        url = SDK_BASE_URL % (SDK_VERSION, fname)

        # strip=True so the inner "ohos-sdk" directory is stripped and contents land in self.prefix
        self.fetch_urls.append((url, None, SDK_CHECKSUMS[os.path.basename(url)]))
        self.extract_steps.append((url, True, os.path.join(self.prefix, 'ohos-sdk')))

    async def start(self, jobs=0):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)

        # Version marker
        try:
            with open(os.path.join(self.prefix, ".ohos-sdk-version"), "w", encoding="utf-8") as fh:
                fh.write(f"{SDK_VERSION}\n")
        except Exception:
            pass

        sdk_dir = os.path.join(self.prefix, 'ohos-sdk')

        if not os.path.isdir(sdk_dir):
            return

        platform_name = _platform_dir_name(self.config.platform)
        platform_dir = os.path.join(sdk_dir, platform_name)
        all_archives = _find_archives_recursively(platform_dir)

        def _comp_of(path: str) -> str:
            base = os.path.basename(path)
            token = base.split(".")[0]
            token = token.split("-")[0].split("_")[0]
            return token

        # Filter to desired components
        archives = [a for a in all_archives if _comp_of(a) in WANTED_COMPONENTS]

        for archive in archives:
            print(f"[OHOS bootstrap] Extracting {archive}")

            comp = _comp_of(archive)
            if not _extract_archive(archive, platform_dir):
                print(f"[OHOS bootstrap] Unknown archive format, skipping: {archive}")
                continue

            source_dir = os.path.join(platform_dir, comp)
            api_version = _read_api_version(source_dir) or "unknown"
            print(f"[OHOS bootstrap] Component={comp}, apiVersion={api_version}")

            target_dir = os.path.join(self.prefix, api_version)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir)

            shutil.move(source_dir, target_dir)

        shutil.rmtree(sdk_dir, ignore_errors=True)

def register_all():
    register_toolchain_bootstrapper(Distro.OHOS, OpenHarmonyBootstrapper)

