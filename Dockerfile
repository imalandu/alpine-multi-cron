FROM alpine:latest
ENV PATH /usr/local/bin:$PATH
ENV LANG C.UTF-8

RUN chmod +x /entrypoint.sh && \
    apk add --no-cache ca-certificates && \
    apk add --no-cache --virtual .fetch-deps gnupg tar xz && \
    wget -O python.tar.xz "https://www.python.org/ftp/python/3.7.1/Python-3.7.1.tar.xz" && \
    mkdir -p /usr/src/python && \
    tar -xJC /usr/src/python --strip-components=1 -f python.tar.xz && \
    rm python.tar.xz && \
    apk add --no-cache --virtual .build-deps bzip2-dev coreutils dpkg-dev dpkg expat-dev \
                                             findutils gcc gdbm-dev libc-dev libffi-dev libnsl-dev \
                                             libressl-dev libtirpc-dev linux-headers make ncurses-dev \
                                             pax-utils readline-dev sqlite-dev tcl-dev tk tk-dev \
                                             util-linux-dev xz-dev zlib-dev && \
    apk del .fetch-deps && \
    cd /usr/src/python && \
    gnuArch="$(dpkg-architecture --query DEB_BUILD_GNU_TYPE)" && \
    ./configure --build="$gnuArch" --enable-loadable-sqlite-extensions --enable-shared \
                --with-system-expat --with-system-ffi --without-ensurepip && \
    make -j "$(nproc)" EXTRA_CFLAGS="-DTHREAD_STACK_SIZE=0x100000" && \
    make install && \
    find /usr/local -type f -executable -not \( -name '*tkinter*' \) -exec scanelf --needed --nobanner --format '%n#p' '{}' ';' \
    | tr ',' '\n' | sort -u | awk 'system("[ -e /usr/local/lib/" $1 " ]") == 0 { next } { print "so:" $1 }' \
    | xargs -rt apk add --no-cache --virtual .python-rundeps && \
    apk del .build-deps && \
    find /usr/local -depth \( \( -type d -a \( -name test -o -name tests \) \) -o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \) -exec rm -rf '{}' + && \
    rm -rf /usr/src/python && \
    python3 --version && \
    cd /usr/local/bin && \
    ln -s idle3 idle && \
    ln -s pydoc3 pydoc && \
    ln -s python3 python && \
    ln -s python3-config python-config && \
    cd && \
    wget -O get-pip.py 'https://bootstrap.pypa.io/get-pip.py' && \
    python get-pip.py --disable-pip-version-check --no-cache-dir "pip==18.1" && \
    pip --version && \
    find /usr/local -depth \( \( -type d -a \( -name test -o -name tests \) \) -o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \) -exec rm -rf '{}' + && \
    rm -f get-pip.py
