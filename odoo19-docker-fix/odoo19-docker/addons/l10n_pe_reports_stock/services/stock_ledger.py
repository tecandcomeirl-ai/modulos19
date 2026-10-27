"""Lógica pura (sin ORM) del kárdex PLE: saldo inicial, entradas/salidas y saldo corrido.

events: lista de dicts ordenados por fecha con las claves
    date, cuo, corr, doc_type, series, number, op, qty_in, qty_out, val_in, val_out
(qty/val en valores positivos; la salida se informa en negativo en el PLE).
"""
from odoo.addons.l10n_pe_reports.services import ple_common as pc


def _q(value, decimals=2):
    return ("%%.%df" % decimals) % (value or 0.0)


def _head(common, ev):
    """Campos 1 a 16 comunes a 12.1 y 13.1."""
    return [
        common["per"], ev["cuo"], ev["corr"], common["estab"], "9", common["existence"], common["code"],
        "1" if common.get("unspsc") else "", common.get("unspsc") or "",
        pc.date(ev["date"]), ev["doc_type"], ev["series"], ev["number"], ev["op"],
        common["desc"], common["uom"]]


def opening_event(common, date):
    return {"date": date, "cuo": "SI%s" % common["pid"], "corr": "M%s" % common["pid"], "doc_type": "00",
            "series": "0", "number": "0", "op": "16"}


def physical_rows(common, opening_qty, events, start_date):
    """Filas del 12.1. La primera tupla es el saldo inicial."""
    rows = []
    ev0 = opening_event(common, start_date)
    rows.append(_head(common, ev0) + [_q(max(opening_qty, 0.0)), "0.00", "1"])
    for ev in events:
        rows.append(_head(common, ev) + [_q(ev["qty_in"]), _q(-ev["qty_out"]) if ev["qty_out"] else "0.00", "1"])
    return rows


def valued_rows(common, method, opening_qty, opening_val, events, start_date):
    """Filas del 13.1 con saldo corrido (cantidad, costo unitario y total)."""
    rows = []
    qty, val = opening_qty, opening_val

    def unit(v, q):
        return (v / q) if q else 0.0

    ev0 = opening_event(common, start_date)
    rows.append(_head(common, ev0) + [method,
                                      _q(max(qty, 0.0), 4), _q(unit(val, qty), 4), _q(max(val, 0.0)),
                                      "0.0000", "0.0000", "0.00",
                                      _q(qty, 4), _q(unit(val, qty), 4), _q(val), "1"])
    for ev in events:
        qty += ev["qty_in"] - ev["qty_out"]
        val += ev["val_in"] - ev["val_out"]
        in_unit = unit(ev["val_in"], ev["qty_in"])
        out_unit = unit(ev["val_out"], ev["qty_out"])
        rows.append(_head(common, ev) + [
            method,
            _q(ev["qty_in"], 4), _q(in_unit, 4), _q(ev["val_in"]),
            _q(-ev["qty_out"], 4) if ev["qty_out"] else "0.0000", _q(out_unit, 4),
            _q(-ev["val_out"]) if ev["val_out"] else "0.00",
            _q(qty, 4), _q(unit(val, qty), 4), _q(val), "1"])
    return rows
