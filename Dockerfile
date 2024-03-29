FROM archlinux:latest

RUN pacman -Sy --noconfirm \
    python \
    fakeroot binutils sudo make \
    gcc patch pkgconf \
    imagemagick

# COPY pkgs/ /var/aur
RUN mkdir /var/aur /opt/distrofonts && \
    chown -R nobody:nobody /var/aur && \
    chown -R nobody:nobody /opt/distrofonts && \
    echo "nobody ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

USER nobody
WORKDIR /tmp

RUN curl -s https://aur.archlinux.org/cgit/aur.git/snapshot/aurutils.tar.gz | tar -zx && \
    cd aurutils && \
    makepkg --syncdeps --install --clean --noconfirm

RUN curl -s https://aur.archlinux.org/cgit/aur.git/snapshot/ttf2png.tar.gz | tar -zx && \
    cd ttf2png && \
    makepkg --syncdeps --install --clean --noconfirm

RUN curl -s https://aur.archlinux.org/cgit/aur.git/snapshot/xorg-font-utils.tar.gz | tar -zx && \
    cd xorg-font-utils && \
    makepkg --syncdeps --install --clean --noconfirm

COPY --chown=nobody:nobody . /opt/distrofonts
WORKDIR /opt/distrofonts

COPY pkgs/ /var/aur

# RUN chown -R nobody:nobody /aurutils
# USER root
# RUN pacman -U aurutils-10b-1-any.pkg.tar.zst

CMD ["/bin/bash"]

# python3 -m http.server 8000