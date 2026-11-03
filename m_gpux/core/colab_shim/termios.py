"""Windows stand-in so google-colab-cli imports; only `colab console` needs the real module."""

TCSADRAIN = TCSANOW = TCSAFLUSH = 0
error = OSError


def tcgetattr(fd):
    raise OSError("termios is unavailable on Windows")


def tcsetattr(fd, when, attrs):
    raise OSError("termios is unavailable on Windows")
