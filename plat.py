"""Platformválasztó: a zenelero.py innen veszi a platformfüggő részeket (Windowson plat_windows, egyébként plat_linux)."""
import sys

if sys.platform == "win32":
    from plat_windows import *  # noqa: F401,F403
else:
    from plat_linux import *  # noqa: F401,F403
