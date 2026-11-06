FROM archlinux:base-devel

# Pacman's seccomp sandbox fails under qemu on Apple Silicon.
RUN echo "DisableSandbox" >> /etc/pacman.conf \
    && pacman -Syu --noconfirm --disable-sandbox \
        python \
        python-pip \
        imagemagick \
        git \
        sudo \
    && useradd --create-home --shell /bin/bash builder \
    && echo "builder ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers \
    && mkdir -p /opt/distrofonts /output \
    && chown builder:builder /opt/distrofonts /output \
    && printf '%s\n' \
        "DLAGENT=('http::/usr/bin/curl -qgC - -fL --retry 10 --retry-delay 2 --retry-all-errors -o %o %u'" \
        "         'https::/usr/bin/curl -qgC - -fL --retry 10 --retry-delay 2 --retry-all-errors -o %o %u'" \
        "         'ftp::/usr/bin/curl -qgC - -fL --retry 10 --retry-delay 2 --retry-all-errors -o %o %u')" \
        >> /etc/makepkg.conf

USER builder
WORKDIR /home/builder

RUN git clone --depth 1 https://aur.archlinux.org/ttf2png.git \
    && cd ttf2png \
    && makepkg --syncdeps --install --noconfirm \
    && cd /home/builder \
    && rm -rf ttf2png

USER root
COPY --chown=builder:builder . /opt/distrofonts
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir /opt/distrofonts

USER builder
WORKDIR /opt/distrofonts
ENV PATH="/opt/venv/bin:${PATH}"
ENTRYPOINT ["archfonts"]
CMD ["--help"]
