"""Portable filenames for trusted paper PDF responses."""

import re
import unicodedata


def build_pdf_filename(title: str, paper_id: str) -> str:
    def clean(value: str) -> str:
        value = unicodedata.normalize('NFC', value)
        value = ''.join('_' if unicodedata.category(char).startswith('C') else char for char in value)
        value = re.sub(r'[<>:"/\\|?*]', '_', value)
        value = re.sub(r'\s+', ' ', value).strip().rstrip('.')
        value = re.sub(r'(?:\.pdf)+$', '', value, flags=re.IGNORECASE).strip(' .')
        # Leave room for the extension within common 255-byte filesystem limits.
        value = value.encode('utf-8')[:180].decode('utf-8', errors='ignore').rstrip(' .')
        if re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value):
            value = '_' + value
        return value

    return f'{clean(title) or clean(paper_id) or "paper"}.pdf'
