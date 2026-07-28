"""Flet build entry point for the native Cloudra application."""

from __future__ import annotations

import flet as ft

from cloudra.ui.app import main

if __name__ == "__main__":
    ft.run(main)
