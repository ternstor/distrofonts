# Distrofonts

Distrofonts builds PNG previews of popular TTF font packages from Linux distributions and writes them into an HTML index. Arch Linux AUR `ttf-*` packages and Debian `fonts-*` / `ttf-*` packages share one generate loop; each distro supplies ranking, fetch, and extract.

The source is released under the MIT license.

## Repeatable Docker run

The supported way to generate an index is the distro image plus Make. By default this keeps going down the popularity ranking until **100 successful** packages are in `dist/<distro>/`. Failed packages are skipped on later runs; already-rendered PNGs are reused.

```bash
make generate                     # Arch Linux (default)
make generate DISTRO=debian       # Debian
```

That builds the image if needed, fetches missing packages into `aur/` or `debian/`, and writes `dist/<distro>/index.html` plus `dist/<distro>/png/`. Interrupted runs resume from whatever is already in `dist/<distro>/`. `aur/`, `debian/`, and `dist/` are gitignored.

```bash
make generate TARGET=100                    # fill until 100 successes (default)
make generate TARGET=100 LIMIT=5            # at most 5 ranked names this run
make generate RESUME=0                      # rebuild instead of reusing png/
make generate FETCH=0                       # do not fetch more packages
make generate RETRY_FAILURES=1              # retry names in failures.txt
make generate DISTRO=debian TARGET=100
make fetch TOP=100                          # cache the top 100 ranked sources
make pages                                  # copy Arch output into ternstor.github.io
make pages DISTRO=debian
```

`make fetch UPDATE=1` refreshes cached sources. Failed packages from a generate run are listed in `dist/<distro>/failures.txt`. `ignore/<distro>.txt` is extra skip-list input.

Arch runs in `archlinux:base-devel` (`linux/amd64`) with AUR `ttf2png`. Debian runs in `debian:stable` and builds `ttf2png` from source. Both include ImageMagick and this package, and run as `builder`. Containers use `--dns 8.8.8.8 --dns 1.1.1.1` so lookups do not go through Docker Desktop's VM resolver.

```bash
python -m http.server -d dist/archlinux
python -m http.server -d dist/debian
```

`index.html` uses relative image URLs and writes `.nojekyll` so GitHub Pages / Jekyll does not drop `_`-prefixed files. `make pages DISTRO=<distro>` copies into `../ternstor.github.io/distrofonts/<distro>/`.

## Usage without Make

```bash
distrofonts fetch --distro archlinux --dest aur --top 100
distrofonts generate --distro archlinux --source-dir aur --output-dir dist/archlinux --target 100 --resume --fetch

distrofonts fetch --distro debian --dest debian --top 100
distrofonts generate --distro debian --source-dir debian --output-dir dist/debian --target 100 --resume --fetch
```

`archfonts` and `archfonts-fetch` remain as aliases that imply `--distro archlinux`.

`--target N` continues until N packages have previews. `--resume` / `--no-resume` reuse or ignore existing PNGs. `--fetch` refreshes ranking and caches the next packages as needed. `--retry-failures` retries `failures.txt` instead of skipping those names. `--limit N` caps how far down the ranking this run considers.

`--skip-integrity` passes `--skipchecksums`, `--skipinteg`, and `--skippgpcheck` to `makepkg` (Arch only). Debian obtains packages with `apt-get download` and `dpkg-deb -x` instead of installing them.

Arch ranking is AUR vote count for `ttf-*`, skipping Microsoft/Apple/WPS vendor families. Debian ranking is popcon `inst` counts for `fonts-*` and leftover `ttf-*`, skipping `*-installer` packages.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```
