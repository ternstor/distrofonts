# Archfonts

Archfonts builds [Arch Linux](https://archlinux.org/) AUR font packages and writes PNG previews of the TTF files into an HTML index.

The source is released under the MIT license.

## Repeatable Docker run

The supported way to generate the index is the Arch Linux image plus Make. By default this keeps going down the AUR vote ranking until **100 successful** packages are in `dist/`, skipping Microsoft/Apple/WPS families that need local vendor files. Failed packages are skipped on later runs; already-rendered PNGs are reused.

```bash
make generate
```

That builds the image if needed, clones any missing packages into `aur/`, and writes `dist/index.html` plus `dist/png/`. Interrupted runs resume from whatever is already in `dist/`. `aur/` and `dist/` are gitignored.

```bash
make generate TARGET=100          # fill until 100 successes (default)
make generate TARGET=100 LIMIT=5  # at most 5 new attempts this run
make generate RESUME=0            # rebuild instead of reusing dist/png
make generate FETCH=0             # do not clone more AUR packages
make generate RETRY_FAILURES=1    # retry names in dist/failures.txt
make fetch TOP=100                # clone the top 100 ranked PKGBUILDs
make publish                      # commit dist/ onto gh-pages locally; does not push
```

`make fetch UPDATE=1` runs `git pull` on clones that already exist. Failed packages from a generate run are listed in `dist/failures.txt`. `ignore.txt` is extra skip-list input; proprietary families are filtered in `archfonts-fetch` before clone.

The image is Arch Linux (`linux/amd64`) with `ttf2png`, ImageMagick, and this package. It runs as `builder`. On Apple Silicon, Docker Desktop emulates that platform. Containers use `--dns 8.8.8.8 --dns 1.1.1.1` so lookups do not go through Docker Desktop's VM resolver, which times out during long `makepkg` download runs. Serve the output with:

```bash
python -m http.server -d dist
```

GitHub Pages can host `dist/` from the `gh-pages` branch. `index.html` uses relative image URLs and writes `.nojekyll` so Jekyll does not drop `_`-prefixed files. After `make publish`:

```bash
git -C .pages push origin gh-pages
```

## Usage without Make

```bash
archfonts-fetch --dest aur --top 100
archfonts --source-dir aur --output-dir dist --target 100 --resume --fetch
```

`--target N` continues until N packages have previews. `--resume` / `--no-resume` reuse or ignore existing PNGs. `--fetch` clones the next most-voted packages as needed. `--retry-failures` retries `failures.txt` instead of skipping those names. `--limit N` caps new attempts in this run.

`--skip-integrity` passes `--skipchecksums`, `--skipinteg`, and `--skippgpcheck` to `makepkg`. The default build verifies checksums and signatures. Package archives may be `.pkg.tar.zst`, `.pkg.tar.xz`, or `.pkg.tar.gz`.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```
