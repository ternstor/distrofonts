#!/bin/sh

# curl -s https://aur.archlinux.org/packages.gz \
#     | gzcat \
#     | grep ttf- \
#     | head -n 10 \
#     | while read -r PKGNAME; do
#         $NOTTF = echo $PKGNAME | 
#         PKGBASE=$(curl -s "https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=$PKGNAME" | grep pkgbase)
#         echo $PKGBASE
#         #curl "https://aur.archlinux.org/cgit/aur.git/snapshot/$PKGBASE.tar.gz" --output "$PKGBASE.tar.gz"
#     done
#     # && wait

#!/usr/bin/python3
import time
from urllib.request import urlopen, urlretrieve
from urllib.error import HTTPError
from gzip import GzipFile
import re
import tarfile
import os.path


PKG_LIST_URL = "https://aur.archlinux.org/packages.gz"
BASE_SNAPSHOT_URL = "https://aur.archlinux.org/cgit/aur.git/snapshot"
STRATEGIES = {
    "plain": lambda x: x,
    "font-postfix": lambda x: x.replace("ttf-", "") + "-font",
    "remove-ttf": lambda x: x.replace("ttf-", ""),
    "otf-instead-ttf": lambda x: x.replace("ttf-", "otf-"),

    "font-prefix": lambda x: x.replace("ttf-", "font-"),
    "fonts-prefix": lambda x: x.replace("ttf-", "fonts-"),
    "font-git-postfix": lambda x: x.replace("ttf-", "").replace("-git", "-font-git"),
    "fonts-git-postfix": lambda x: x.replace("ttf-", "").replace("-git", "-fonts-git"),

    "variable.font-postfix-remove-variable": lambda x: x.replace("ttf-", "").replace("-variable", "") + "-font",
    "variable.remove-variable": lambda x: x.replace("ttf-", "").replace("-variable", ""),
    "variable.replace-variable-with-font": lambda x: x.replace("ttf-", "").replace("-variable", "-font"),

    "desktop.font-postfix-remove-desktop": lambda x: x.replace("ttf-", "").replace("-desktop", "") + "-font",
    "desktop.remove-desktop": lambda x: x.replace("ttf-", "").replace("-desktop", ""),
    "desktop.replace-desktop-with-font": lambda x: x.replace("ttf-", "").replace("-desktop", "-font"),
}
COUNTS = dict(zip(STRATEGIES.keys(), len(STRATEGIES) * [0,]))
PKG_TO_BASE_MAP = {}


def write_output():
    print(COUNTS)
    print(len(WTFS))

    with open("wtfs.txt", "w") as wtfs:
        for wtf in WTFS:
            wtfs.write(f"{wtf}\n")

    with open("names.txt", "w") as names:
        for pkg_name, base_name in PKG_TO_BASE_MAP.items():
            names.write(f"{pkg_name},{base_name}\n")


with urlopen(PKG_LIST_URL) as packages:
    all_pkg_names = GzipFile(fileobj=packages).readlines()

font_pkg_names = []
for pkg_name in all_pkg_names:
    clean_pkg_name = pkg_name.decode("utf-8").strip()
    if re.match("ttf-.*", clean_pkg_name):
        font_pkg_names += [clean_pkg_name]

try:
    WTFS = []
    for font_pkg_name in font_pkg_names:

        already_exists = False
        for strategy_name, strategy_func in STRATEGIES.items():
            base_name = strategy_func(font_pkg_name)
            if os.path.exists(f"./pkgs/{base_name}"):
                COUNTS[strategy_name] += 1
                PKG_TO_BASE_MAP[font_pkg_name] = base_name
                already_exists = True
                break

        if already_exists:
            print()
            print(f"Skipping: {font_pkg_name}")
            continue


        print()
        print(f"Trying for: {font_pkg_name}")

        success = False
        urls_tried = set()
        for strategy_name, strategy_func in STRATEGIES.items():
            base_name = strategy_func(font_pkg_name)
            pkg_url = f"{BASE_SNAPSHOT_URL}/{base_name}.tar.gz"

            if pkg_url in urls_tried:
                continue

            if "variable" not in font_pkg_name and strategy_name.startswith("variable."):
                continue

            if "desktop" not in font_pkg_name and strategy_name.startswith("desktop."):
                continue

            try:
                local_file_name, _ = urlretrieve(pkg_url)
            except HTTPError as ex:
                urls_tried.add(pkg_url)
                if ex.status == 404:
                    print(f"Failed: {pkg_url}")
                    continue
                    # 429 too many requests
                else:
                    write_output()
                    raise

            pkg = tarfile.open(local_file_name)
            pkg.extractall(f"./pkgs/")

            print(f"Success: {pkg_url}")
            success = True
            COUNTS[strategy_name] += 1
            PKG_TO_BASE_MAP[font_pkg_name] = base_name
            time.sleep(5)
            break

        if not success:
            print(f"WTF: {font_pkg_name}")
            WTFS += [font_pkg_name]
            time.sleep(5)
except KeyboardInterrupt:
    write_output()
    raise    

write_output()