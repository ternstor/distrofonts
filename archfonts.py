#!/usr/bin/python3

"""
Archfonts is a script and module to generate PNG images from TTF fonts
found in [Archlinux](http://www.archlinux.org/) AUR or ABS source
trees.

Prebuilt indexes:

* AUR: [online](http://ternstor.github.com/archfonts/aur.html),
[gzip](http://ternstor.github.com/archfonts/aur.tar.gz).
* ABS:
    * Community: [online](http://ternstor.github.com/archfonts/community.html),
    [gzip](http://ternstor.github.com/archfonts/community.tar.gz).
    * Extra: [online](http://ternstor.github.com/archfonts/extra.html)
    [gzip](http://ternstor.github.com/archfonts/extra.tar.gz).

Dependencies: ttf2png, pacman (makepkg), imagemagick.

The [source for archfonts](http://github.com/ternstor/archfonts) is
available on GitHub, and released under the MIT license.
"""

import glob
import shutil
import os.path
import subprocess
import fnmatch
import sys
import argparse
import logging
from typing import List, Dict

import outputs

from string import Template

MAKEPKG_CMD = [
    "makepkg",
    "--force",
    "--syncdeps",
    "--ignorearch",
    "--nocolor",
    "--noconfirm",
    "--skipchecksums",
    "--skipinteg",
    "--skippgpcheck",
]
# Never add --clean.

# **ttf2png** options: font size 20 px.
TTF2PNG_CMD = ["ttf2png", "-s", "20"]

IGNORE_FILE = os.path.join(sys.path[0], "ignore.txt")
IGNORE_LIST = ["ttf-win10"]


class ArchFontPackage(object):

    """
    Main class for an Archlinux font package.

    It receives a package directory `pkg_dir` containing a PKGBUILD and
    possible other files, as specified by ABS and AUR.
    """

    def __init__(self, pkg_dir):
        """Initialize package directories and ignore list."""

        self.pkg_name = os.path.basename(pkg_dir)
        self.pkg_dir = pkg_dir
        self.failed = []
        self.logger = logging.getLogger(self.pkg_name)

        if os.path.exists(IGNORE_FILE):
            with open(IGNORE_FILE) as ignore_file:
                self.ignore_list = ignore_file.readlines()
                self.ignore_list = list(map(lambda x: x.strip(), self.ignore_list))
                self.ignore_list = IGNORE_LIST + self.ignore_list
        else:
            self.ignore_list = []

    def _run(self, command):
        process = subprocess.run(command, capture_output=True)

        if process.stderr and process.returncode:
            self.logger.error(
                "Error running '%s' for '%s':\n%s\n",
                " ".join(command),
                self.pkg_name,
                process.stderr,
            )

        return process.returncode

    def copy(self, dest_dir):
        """Copy the package to a destination directory."""

        try:
            shutil.copytree(self.pkg_dir, dest_dir)
        except:  # error 17 mkdir
            pass

        self.pkg_dir = dest_dir

    def ignore_pkg(self):
        """Add a package to an ignore list and ignore file."""

        with open(IGNORE_FILE, "a") as ignore_file:
            ignore_file.write(self.pkg_name + "\n")

    def make_pkg(self):
        """Build the package and return the exit code."""
        os.chdir(self.pkg_dir)
        return self._run(MAKEPKG_CMD)

    def extract_pkg(self):
        """Uncompress the package and return the exit code."""

        xz_pkgs = glob.glob(os.path.join(self.pkg_dir, "*.tar.xz"))

        if xz_pkgs:
            os.chdir(self.pkg_dir)
            return self._run(["tar", "-Jxf", xz_pkgs[0]])
        else:
            return False

    def get_ttfs(self):
        """Return list of ttf file paths found for the package."""

        ttf_paths = []

        for root, _, filenames in os.walk(self.pkg_dir):
            for filename in fnmatch.filter(filenames, "*.ttf"):
                ttf_paths.append(os.path.join(root, filename))
        return ttf_paths

    def to_pngs(self, ttf_paths):
        """Transform ttf files to png and return these png file paths."""

        png_paths = []

        for ttf_path in ttf_paths:
            output_png = ttf_path + ".png"
            command = TTF2PNG_CMD[:]
            command.extend(["-o", output_png, ttf_path])
            ret_code = self._run(command)
            if ret_code == 0:
                png_paths.append(output_png)
            else:
                self.failed.append(ttf_path)

        return png_paths

    def trim_pngs(self, png_paths):
        """Trim generated PNGs using ImageMagick's convert."""

        for png_path in png_paths:
            self._run(["convert", "-trim", png_path, png_path])


def output(
    ttfs: Dict[str, List[str]],
    output_format: str,
):
    """Write output file using pkg -> path dictionary."""
    here = sys.path[0]
    tpl_path = os.path.join("templates", output_format)
    output_func = getattr(outputs, output_format)

    output_dict = {"content": output_func(ttfs), "source_dir": args.source_dir}

    with open(os.path.join(here, tpl_path)) as tpl_file, open(
        os.path.join(here, "out.html"), "w"
    ) as output_html_file:

        tpl_content = open(tpl_file).read()
        html = Template(tpl_content).substitute(output_dict)
        output_html_file.write(html)


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Build PNG files from TTF packages in AUR."
    )
    parser.add_argument("-o", "--output", type=str, default="html", help="output type")
    parser.add_argument(
        "-s",
        "--source-dir",
        type=str,
        default="/var/aur",
        help="directory where ABS/AUR packages live",
    )
    parser.add_argument(
        "-b",
        "--build-dir",
        type=str,
        default="/tmp/archfonts",
        help="directory where packages will be copied/built",
    )

    args = parser.parse_args()

    # Get all ttf packages from the AUR clone.
    pkg_dirs = glob.glob(os.path.join(args.source_dir, "ttf-*"))[:4]
    ttfs = {}
    n = len(pkg_dirs)

    for i, pkg_dir in enumerate(pkg_dirs):
        archfont = ArchFontPackage(pkg_dir)
        pkg_name = archfont.pkg_name

        # Ignore the package if it failed previously.
        # This avoids extra work in multiple runs.

        if pkg_name in archfont.ignore_list:
            logging.info("[%d/%d] Ignoring %s", i, n, pkg_name)
            continue

        # Copy to our build directory
        pkg_dir = os.path.join(args.build_dir, pkg_name)
        archfont.copy(pkg_dir)

        # Try to make the package, add to ignore list if it fails.
        logging.info("[%d/%d] Processing %s", i, n, pkg_name)
        ret_code = archfont.make_pkg()

        if ret_code != 0:
            archfont.ignore_pkg()
            logging.info("[%d/%d] Adding %s to %s", i, n, pkg_name, IGNORE_FILE)
            continue

        # Extract the package we just made, find ttfs and dict' them.
        archfont.extract_pkg()
        ttf_paths = archfont.get_ttfs()
        ttfs[pkg_name] = archfont.to_pngs(ttf_paths)
        archfont.trim_pngs(ttfs[pkg_name])

    # Write using the html template.
    output(ttfs, args.output)
