IMAGE ?= archfonts
PLATFORM ?= linux/amd64
DOCKER_RUN = docker run --rm --platform $(PLATFORM) --security-opt seccomp=unconfined \
	--dns 8.8.8.8 --dns 1.1.1.1
AUR_DIR ?= $(CURDIR)/aur
DIST_DIR ?= $(CURDIR)/dist
PAGES_DIR ?= $(CURDIR)/.pages
SITE_DIR ?= $(CURDIR)/../ternstor.github.io
SITE_DEST ?= $(SITE_DIR)/distrofonts/archlinux
TOP ?= 100
TARGET ?= 100
IGNORE_FILE ?= $(CURDIR)/ignore.txt

ifdef LIMIT
LIMIT_FLAG := --limit $(LIMIT)
endif
ifdef SKIP_INTEGRITY
INTEGRITY_FLAG := --skip-integrity
endif
ifdef UPDATE
UPDATE_FLAG := --update
endif
ifeq ($(RESUME),0)
RESUME_FLAG := --no-resume
else
RESUME_FLAG := --resume
endif
ifeq ($(FETCH),0)
FETCH_FLAG := --no-fetch
else
FETCH_FLAG := --fetch
endif
ifeq ($(RETRY_FAILURES),1)
RETRY_FLAG := --retry-failures
else
RETRY_FLAG := --no-retry-failures
endif

.PHONY: help docker-build fetch generate index pages publish clean clean-all

help:
	@echo "make index          Fetch and generate until TARGET successful packages"
	@echo "make fetch          Clone the TOP most-voted ttf-* packages into aur/"
	@echo "make generate       Resume PNG generation until TARGET successes"
	@echo "make pages          Copy index.html and pngs into ../ternstor.github.io/"
	@echo "make publish        Commit dist/ onto the gh-pages worktree (no push)"
	@echo "make clean          Remove dist/"
	@echo "make clean-all      Remove dist/ and aur/"
	@echo "Variables: TOP=$(TOP) TARGET=$(TARGET) LIMIT RESUME=0 FETCH=0 RETRY_FAILURES=1"

docker-build:
	docker build --platform $(PLATFORM) -t $(IMAGE) .

fetch: docker-build
	mkdir -p $(AUR_DIR)
	$(DOCKER_RUN) --entrypoint archfonts-fetch \
		-v $(AUR_DIR):/var/aur \
		$(IMAGE) --dest /var/aur --top $(TOP) $(UPDATE_FLAG)

generate: docker-build
	mkdir -p $(AUR_DIR) $(DIST_DIR)
	$(DOCKER_RUN) \
		-v $(AUR_DIR):/var/aur \
		-v $(DIST_DIR):/output \
		-v $(IGNORE_FILE):/opt/distrofonts/ignore.txt:ro \
		$(IMAGE) --source-dir /var/aur --output-dir /output \
		--target $(TARGET) $(RESUME_FLAG) $(FETCH_FLAG) $(RETRY_FLAG) \
		$(LIMIT_FLAG) $(INTEGRITY_FLAG)

index: generate

pages:
	@test -f $(DIST_DIR)/index.html || (echo "Run make generate first" >&2; exit 1)
	@test -d $(DIST_DIR)/png || (echo "Missing $(DIST_DIR)/png" >&2; exit 1)
	@test -d $(SITE_DIR) || (echo "Missing GitHub Pages repo: $(SITE_DIR)" >&2; exit 1)
	mkdir -p $(SITE_DEST)
	rsync -a --delete --exclude .git --exclude failures.txt \
		$(DIST_DIR)/ $(SITE_DEST)/
	touch $(SITE_DEST)/.nojekyll
	@echo "Copied to $(SITE_DEST)"
	@echo "Commit and push ternstor.github.io for https://ternstor.github.io/distrofonts/archlinux/"

publish:
	@test -f $(DIST_DIR)/index.html || (echo "Run make generate first" >&2; exit 1)
	git fetch origin gh-pages
	@if git worktree list | grep -q '\[gh-pages\]'; then \
		echo "Using existing gh-pages worktree"; \
	else \
		git worktree add $(PAGES_DIR) gh-pages; \
	fi
	rsync -a --delete --exclude .git --exclude failures.txt $(DIST_DIR)/ $(PAGES_DIR)/
	touch $(PAGES_DIR)/.nojekyll
	git -C $(PAGES_DIR) add -A
	git -C $(PAGES_DIR) diff --cached --quiet \
		|| git -C $(PAGES_DIR) commit -m "Publish font index"
	@echo "gh-pages updated locally. Push with: git -C $(PAGES_DIR) push origin gh-pages"

clean:
	rm -rf $(DIST_DIR)

clean-all: clean
	rm -rf $(AUR_DIR)
