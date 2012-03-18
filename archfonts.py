#!/usr/bin/python3

"""
Archfonts is a script and module to generate PNG images from TTF fonts
found in [Archlinux](http://www.archlinux.org/) AUR or ABS source
trees.

It searches for package names that follow the
[suggested](https://wiki.archlinux.org/index.php/Fonts) `ttf-fontname`
pattern.

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

import outputs

from string import Template

# **makepkg** options: force, syncdeps, clean, ignore arch, no colors.
MAKEPKG_CMD = ['makepkg', '-f', '-s', '-c', '-A', '--nocolor']
# **ttf2png** options: font size 20 px.
TTF2PNG_CMD = ['ttf2png', '-s', '20']

IGNORE_FILE = os.path.join(sys.path[0], 'ignore.txt')

# === Archlinux Font Package Class ===

class ArchFontPackage(object):

    """
    Main class for an Archlinux font package.

    It receives a package directory `pkg_dir` containing a PKGBUILD and
    possible other files, as specified by ABS and AUR.
    """

    def __init__(self, pkg_dir, err_filename='makepkg.stderr.log'):
        """Initialize package directories and ignore list."""

        self.pkg_name = os.path.basename(pkg_dir)
        self.pkg_dir = pkg_dir
        self.status = {}
        self.err_file = open(err_filename, 'a')
        self.failed = []

        if os.path.exists(IGNORE_FILE):
            self.ignore_list = open(IGNORE_FILE).readlines()
            self.ignore_list = list(map(lambda x: x.strip(), self.ignore_list))
        else:
            self.ignore_list = []

    def __del__(self):
        self.err_file.close()

    def copy(self, dest_dir):
        """Copy the package to a destination directory."""

        try:
            shutil.copytree(self.pkg_dir, dest_dir)
        except: # error 17 mkdir
            pass

        self.pkg_dir = dest_dir

    def ignore_pkg(self):
        """Add a package to an ignore list and ignore file."""

        with open(IGNORE_FILE, 'a') as ignore_file:
            ignore_file.write(self.pkg_name + '\n')

    def make_pkg(self):
        """Build the package and return the exit code."""
        os.chdir(self.pkg_dir)
        return subprocess.call(MAKEPKG_CMD, stderr=self.err_file)

    def extract_pkg(self):
        """Uncompress the package and return the exit code."""

        xz_pkgs = glob.glob(os.path.join(self.pkg_dir, '*.tar.xz'))

        if xz_pkgs:
            os.chdir(self.pkg_dir)
            return subprocess.call(['tar', '-Jxf', xz_pkgs[0]])
        else:
            return False

    def get_ttfs(self):
        """Return list of ttf file paths found for the package."""

        ttf_paths = []

        for root, dirnames, filenames in os.walk(self.pkg_dir):
            for filename in fnmatch.filter(filenames, '*.ttf'):
                ttf_paths.append(os.path.join(root, filename))

        return ttf_paths

    def to_pngs(self, ttf_paths):
        """Transform ttf files to png and return these png file paths."""

        png_paths = []

        for ttf_path in ttf_paths:
            output_png = ttf_path + '.png'
            command = TTF2PNG_CMD[:]
            command.extend(['-o', output_png, ttf_path])
            ret_code = subprocess.call(command)
            if ret_code == 0:
                png_paths.append(output_png)
            else:
                self.failed.append(ttf_path)

        return png_paths

    def trim_pngs(self, png_paths):
        """Trim generated PNGs using ImageMagick's convert."""

        for png_path in png_paths:
            subprocess.call(['convert', '-trim', png_path, png_path])

# === Output helper function ===

def output(ttfs, output_format):
    """Write output file using pkg -> path dictionary."""
    here = sys.path[0]
    tpl_path = os.path.join('templates', output_format)
    abs_tpl_path = os.path.join(here, tpl_path)
    output_func = getattr(outputs, output_format)

    tpl_content = open(abs_tpl_path).read()
    output_dict = {'content': output_func(ttfs),
                   'source_dir': args.source_dir}
    html = Template(tpl_content).substitute(output_dict)
    open(os.path.join(here, 'out.html'), 'w').write(html)

# === Main execution ===

if __name__ == '__main__':

    # **TODO:** Get output filename and stderr output file.

    parser = argparse.ArgumentParser(
                        description='Build PNG files from TTF packages in AUR.')
    parser.add_argument('-o', '--output', type=str,
                        default='html', help='output type')
    parser.add_argument('-s', '--source-dir', type=str,
                        default='/var/aur',
                        help='directory where ABS/AUR packages live')
    parser.add_argument('-b', '--build-dir', type=str,
                        default='/tmp/archfonts',
                        help='directory where packages will be copied/built')

    args = parser.parse_args()

    # Get all ttf packages from the AUR clone.
    pkg_dirs = glob.glob(os.path.join(args.source_dir, 'ttf-*'))
    ttfs = {}

    for pkg_dir in pkg_dirs:
        archfont = ArchFontPackage(pkg_dir)
        pkg_name = archfont.pkg_name

        # Ignore the package if it failed previously.
        # This avoids extra work in multiple runs.

        if pkg_name in archfont.ignore_list:
            continue

        # Copy to our build directory
        pkg_dir = os.path.join(args.build_dir, pkg_name)
        archfont.copy(pkg_dir)

        # Try to make the package, add to ignore list if it fails.
        ret_code = archfont.make_pkg()

        if ret_code != 0:
            archfont.ignore_pkg()
            continue

        # Extract the package we just made, find ttfs and dict' them.
        archfont.extract_pkg()
        ttf_paths = archfont.get_ttfs()
        ttfs[pkg_name] = archfont.to_pngs(ttf_paths)
        archfont.trim_pngs(ttfs[pkg_name])

    # Write using the html template.
    output(ttfs, args.output)
