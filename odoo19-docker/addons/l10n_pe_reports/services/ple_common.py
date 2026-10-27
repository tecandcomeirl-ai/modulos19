"""Utilidades de formato para los libros electrónicos PLE."""
import re

SEP = "|"


def clean(text, maxlen=None):
    """Texto seguro para PLE: sin palotes, '&' ni saltos de línea."""
    value = re.sub(r"[|&\r\n\t]+", " ", text or "").strip()
    return value[:maxlen] if maxlen else value


def amount(value):
    return "%.2f" % (value or 0.0)


def date(value):
    return value.strftime("%d/%m/%Y") if value else ""


def period(year, month):
    return "%04d%02d00" % (year, month)


def record(fields):
    """Línea PLE: campos separados y terminados en palote."""
    return SEP.join(str(f) if f is not None else "" for f in fields) + SEP


def file_name(ruc, year, month, book, has_data, currency="1"):
    """LE + RUC + AAAAMM + 00 + libro(6) + 00 + O + I + M + 1 + .txt (Anexo 2 RS 286-2009)."""
    return "LE%s%04d%02d00%s00%s%s%s1.txt" % (
        ruc, year, month, book, "1", "1" if has_data else "0", currency)
