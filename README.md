# debianxrdp

Debian Bullseye + XFCE4 + XRDP + Wine in Docker. Connect via any RDP client on port 3389.

## Build

```bash
docker build -t debianxrdp .
```

## Run

```bash
docker run -d -p 3389:3389 -v xrdp-root-home:/root --name xrdp debianxrdp
```

## Connect

- Host: your IP or Railway domain
- Port: `3389`
- User: `root`
- Pass: `SODOHU`
