"""Windows stand-in so google-colab-cli imports (see termios.py)."""


def setraw(fd, when=None):
    raise OSError("tty is unavailable on Windows")


def setcbreak(fd, when=None):
    raise OSError("tty is unavailable on Windows")
