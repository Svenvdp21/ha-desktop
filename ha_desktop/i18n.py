"""Vertalingen. De brontekst is Engels; translations.py bevat het Nederlands.

Taal volgt het systeem; HA_DESKTOP_LANG=en|nl dwingt een taal af.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QLocale

SUPPORTED = ("en", "nl")
_lang: str | None = None


def language() -> str:
    global _lang
    if _lang is None:
        forced = os.environ.get("HA_DESKTOP_LANG", "")[:2].lower()
        if forced in SUPPORTED:
            _lang = forced
        else:
            _lang = "nl" if QLocale.system().language() == QLocale.Language.Dutch else "en"
    return _lang


def set_language(code: str) -> None:
    global _lang
    _lang = code


def _(text: str) -> str:
    if language() == "nl":
        from ha_desktop.translations import NL

        return NL.get(text, text)
    return text


def N_(text: str) -> str:
    """Markeert tekst als vertaalbaar zonder te vertalen (voor constanten)."""
    return text
