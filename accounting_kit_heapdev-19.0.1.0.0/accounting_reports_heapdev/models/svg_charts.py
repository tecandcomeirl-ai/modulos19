# -*- coding: utf-8 -*-
"""Tiny dependency-free SVG charts rendered server side (identical on Odoo 14-20, screen and PDF)."""
from odoo import models


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _short(v):
    a = abs(v)
    if a >= 1e6:
        return "%.1fM" % (v / 1e6)
    if a >= 1e3:
        return "%.0fK" % (v / 1e3)
    return "%.0f" % v


class AccReportEngineCharts(models.AbstractModel):
    _inherit = "acc.report.engine"

    def _svg_bars(self, labels, series, colors, height=230, width=600):
        """Grouped vertical bars. series: list of (name, [values])."""
        n = max(len(labels), 1)
        vmax = max([abs(v) for _n, vals in series for v in vals] + [1.0])
        pad_l, pad_b, pad_t = 52, 26, 10
        ch, cw = height - pad_b - pad_t, width - pad_l - 8
        gw = cw / float(n)
        bw = max(4.0, (gw - 10) / max(len(series), 1))
        out = ['<svg class="o_acc_svg" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">' % (width, height)]
        for i in range(5):
            y = pad_t + ch * i / 4.0
            out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e8edf3"/>' % (pad_l, y, width - 8, y))
            out.append('<text x="%d" y="%.1f" font-size="10" fill="#8593a3" text-anchor="end">%s</text>' % (pad_l - 6, y + 3, _short(vmax * (1 - i / 4.0))))
        for gi, label in enumerate(labels):
            x0 = pad_l + gi * gw + 5
            for si, (name, vals) in enumerate(series):
                v = vals[gi] if gi < len(vals) else 0.0
                h = ch * abs(v) / vmax
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"><title>%s %s: %s</title></rect>'
                           % (x0 + si * bw, pad_t + ch - h, max(bw - 3, 2), h, colors[si % len(colors)], _esc(label), _esc(name), "{:,.2f}".format(v)))
            out.append('<text x="%.1f" y="%d" font-size="10" fill="#5d6b7a" text-anchor="middle">%s</text>' % (pad_l + gi * gw + gw / 2, height - 8, _esc(label)))
        out.append("</svg>")
        return "".join(out)

    def _svg_hbars(self, items, color="#2b7de9", width=520, row_h=30):
        vmax = max([abs(v) for _l, v in items] + [1.0])
        height = max(row_h * len(items), row_h)
        out = ['<svg class="o_acc_svg" viewBox="0 0 %d %d" preserveAspectRatio="xMinYMin meet" xmlns="http://www.w3.org/2000/svg">' % (width, height)]
        for i, (label, v) in enumerate(items):
            y = i * row_h
            w = (width - 250) * abs(v) / vmax
            out.append('<text x="0" y="%d" font-size="12" fill="#2f3e4d">%s</text>' % (y + 19, _esc((label or "")[:26])))
            out.append('<rect x="170" y="%d" width="%.1f" height="16" rx="4" fill="%s"/>' % (y + 7, max(w, 2), color))
            out.append('<text x="%.1f" y="%d" font-size="11" fill="#2f3e4d">%s</text>' % (176 + w, y + 19, "{:,.0f}".format(v)))
        out.append("</svg>")
        return "".join(out)

    def _svg_donut(self, items, colors, size=170):
        total = sum(max(v, 0) for _l, v in items) or 1.0
        r, c, sw = 60, size / 2.0, 24
        circ = 2 * 3.14159265 * r
        out = ['<svg class="o_acc_svg o_acc_donut" viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg">' % (size, size),
               '<circle cx="%.1f" cy="%.1f" r="%d" fill="none" stroke="#eef2f6" stroke-width="%d"/>' % (c, c, r, sw)]
        offset = 0.0
        for i, (label, v) in enumerate(items):
            frac = max(v, 0) / total
            if frac <= 0:
                continue
            out.append('<circle cx="%.1f" cy="%.1f" r="%d" fill="none" stroke="%s" stroke-width="%d" stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f" transform="rotate(-90 %.1f %.1f)"><title>%s</title></circle>'
                       % (c, c, r, colors[i % len(colors)], sw, frac * circ, circ, -offset * circ, c, c, _esc(label)))
            offset += frac
        out.append("</svg>")
        return "".join(out)

    def _svg_line(self, labels, values, color="#12a37f", height=210, width=600):
        n = max(len(values), 2)
        vmin, vmax = min(list(values) + [0.0]), max(list(values) + [1.0])
        span = (vmax - vmin) or 1.0
        pad_l, pad_b, pad_t = 52, 24, 10
        ch, cw = height - pad_b - pad_t, width - pad_l - 14
        pts = [(pad_l + cw * i / float(n - 1), pad_t + ch * (1 - (v - vmin) / span)) for i, v in enumerate(values)]
        out = ['<svg class="o_acc_svg" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">' % (width, height)]
        for i in range(5):
            y = pad_t + ch * i / 4.0
            out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e8edf3"/>' % (pad_l, y, width - 14, y))
            out.append('<text x="%d" y="%.1f" font-size="10" fill="#8593a3" text-anchor="end">%s</text>' % (pad_l - 6, y + 3, _short(vmax - span * i / 4.0)))
        if pts:
            base = pad_t + ch * (1 - (0 - vmin) / span)
            area = "M%.1f,%.1f " % (pts[0][0], base) + " ".join("L%.1f,%.1f" % p for p in pts) + " L%.1f,%.1f Z" % (pts[-1][0], base)
            out.append('<path d="%s" fill="%s" fill-opacity="0.13"/>' % (area, color))
            out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>' % (" ".join("%.1f,%.1f" % p for p in pts), color))
            for (x, y), v in zip(pts, values):
                out.append('<circle cx="%.1f" cy="%.1f" r="3.3" fill="#fff" stroke="%s" stroke-width="2"><title>%s</title></circle>' % (x, y, color, "{:,.2f}".format(v)))
        for i, label in enumerate(labels):
            if i < len(pts):
                out.append('<text x="%.1f" y="%d" font-size="10" fill="#5d6b7a" text-anchor="middle">%s</text>' % (pts[i][0], height - 7, _esc(label)))
        out.append("</svg>")
        return "".join(out)
