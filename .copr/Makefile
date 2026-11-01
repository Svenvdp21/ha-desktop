# Voor Fedora COPR, bouwmethode "make_srpm": maakt de SRPM rechtstreeks uit deze git-repo.
# Lokaal testen: make -f .copr/Makefile srpm outdir=/tmp/srpm
# Paden staan tussen aanhalingstekens, zodat ook mappen met spaties werken.
TOP := $(dir $(lastword $(MAKEFILE_LIST))).
outdir ?= $(TOP)/../dist
spec ?= $(TOP)/../packaging/ha-desktop.spec

srpm:
	command -v git >/dev/null || dnf -y install git
	command -v rpmbuild >/dev/null || dnf -y install rpm-build
	set -e; \
	root="$$(cd "$(TOP)/.." && pwd)"; \
	out="$$(mkdir -p "$(outdir)" && cd "$(outdir)" && pwd)"; \
	version="$$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$$root/ha_desktop/__init__.py")"; \
	git -C "$$root" -c safe.directory='*' archive --format=tar.gz --prefix="ha-desktop-$$version/" \
		-o "$$out/ha-desktop-$$version.tar.gz" HEAD; \
	rpmbuild -bs "$(spec)" --define "_sourcedir $$out" --define "_srcrpmdir $$out"

.PHONY: srpm
