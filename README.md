# Archfonts

Archfonts is a script and module to generate PNG images from TTF fonts
found in [Archlinux](http://www.archlinux.org/) AUR or ABS source
trees.

The [source for archfonts](http://github.com/ternstor/archfonts) is
available on GitHub, and released under the MIT license.

## Prebuilt indexes

* AUR: [online](http://ternstor.github.com/archfonts/aur.html),
[gzip](http://ternstor.github.com/archfonts/aur.tar.gz).
* ABS: 
    * Community: [online](http://ternstor.github.com/archfonts/community.html),
    [gzip](http://ternstor.github.com/archfonts/community.tar.gz).
    * Extra: [online](http://ternstor.github.com/archfonts/extra.tar.gz),
    [gzip](http://ternstor.github.com/archfonts/extra.html)

## Dependencies

* ttf2png
* pacman (makepkg)
* imagemagick

## Usage

	usage: archfonts.py [-h] [-o OUTPUT] [-s SOURCE_DIR] [-b BUILD_DIR]

	Build PNG files from TTF packages in AUR.

	optional arguments:
	  -h, --help            show this help message and exit
	  -o OUTPUT, --output OUTPUT
		                output type
	  -s SOURCE_DIR, --source-dir SOURCE_DIR
		                directory where ABS/AUR packages live
	  -b BUILD_DIR, --build-dir BUILD_DIR
		                directory where packages will be copied/built
