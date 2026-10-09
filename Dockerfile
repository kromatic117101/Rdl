FROM debian:bullseye-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN dpkg --add-architecture i386 && apt-get update

RUN apt-get install -y --no-install-recommends \
    xrdp \
    xfce4 \
    xfce4-goodies \
    xorg \
    dbus-x11 \
    sudo \
    curl \
    wget \
    nano \
    net-tools \
    polkit \
    pulseaudio \
    pulseaudio-utils \
    wine \
    firefox-esr && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set root password
RUN echo "root:SODOHU" | chpasswd

RUN sed -i 's/^allowed_users=.*/allowed_users=anybody/' /etc/X11/Xwrapper.config \
    || echo "allowed_users=anybody" >> /etc/X11/Xwrapper.config

RUN echo "startxfce4" > /root/.xsession && chmod 700 /root/.xsession

# Generate machine-id for dbus
RUN mkdir -p /var/run/dbus && dbus-uuidgen > /var/lib/dbus/machine-id

RUN sed -i 's/crypt_level=high/crypt_level=low/' /etc/xrdp/xrdp.ini && \
    sed -i 's/security_layer=negotiate/security_layer=rdp/' /etc/xrdp/xrdp.ini && \
    echo "exec startxfce4" > /etc/xrdp/startwm.sh && chmod +x /etc/xrdp/startwm.sh

RUN adduser xrdp ssl-cert

COPY start.sh /start.sh
COPY pulse-client.conf /etc/pulse/client.conf

RUN chmod +x /start.sh

EXPOSE 3389
CMD ["/start.sh"]
