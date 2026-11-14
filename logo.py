"""Das Ring-Logo (aus NoTime übernommen) (konzentrische Ringe mit Lücken) – als Vektor gerechnet, damit es
in jeder Größe scharf ist. Nur numpy, kein Pillow."""
import base64
import struct
import zlib

import numpy as np

TAU = 2 * np.pi


def _layout(px):
    """Kleine Größen bekommen weniger, dafür kräftigere Ringe – sonst wird es Pixelbrei."""
    if px >= 160:
        n = 9
    elif px >= 64:
        n = 6
    elif px >= 40:
        n = 5
    elif px >= 28:
        n = 4
    else:
        n = 3
    inner, outer = (0.22, 0.95) if n >= 6 else (0.30, 0.93)
    radii = np.linspace(inner, outer, n)
    step = (outer - inner) / max(1, n - 1)
    # Strichstärke mindestens ~1,4 echte Pixel
    stroke = max(step * 0.50, 2.8 / px)
    rng = np.random.default_rng(11)
    gaps = []
    for i in range(n):
        if i == 0:
            gaps.append([])
            continue
        k = 1 if n <= 4 else 1 + int(rng.integers(0, 2))
        base = rng.uniform(0, TAU)
        gaps.append([(base + j * TAU / k) % TAU for j in range(k)])
    return radii, stroke, gaps


def rings_alpha(px, scale=1.0, ss=4):
    radii, stroke, gaps = _layout(px)
    s = px * ss
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    x = (x + 0.5) / s * 2 - 1
    y = (y + 0.5) / s * 2 - 1
    r = np.hypot(x, y) / scale
    th = np.arctan2(y, x)
    alpha = np.zeros((s, s), np.float32)
    n = len(radii)
    gap_len = stroke * (1.9 if n > 4 else 2.4)
    for i, R in enumerate(radii):
        ring = np.abs(r - R) <= stroke / 2
        for g in gaps[i]:
            d = (th - g + np.pi) % TAU - np.pi
            ring &= np.abs(d) * R > gap_len / 2
        weight = 0.55 + 0.45 * (i / max(1, n - 1)) ** 0.8 if n > 4 else 1.0
        alpha = np.maximum(alpha, ring * weight)
    return alpha.reshape(px, ss, px, ss).mean(axis=(1, 3))


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


_ALPHA_CACHE = {}


def render(px, color, dot=None, dot_ring=None):
    """Logo in `color`. Optional kleiner Aufnahme-Punkt (dot=Farbe) unten rechts."""
    a = _ALPHA_CACHE.get(px)
    if a is None:
        a = _ALPHA_CACHE[px] = rings_alpha(px)
    img = np.zeros((px, px, 4), np.float32)
    img[..., :3] = _rgb(color)
    img[..., 3] = a * 255
    if dot:
        ss = 4
        s = px * ss
        y, x = np.mgrid[0:s, 0:s].astype(np.float32)
        d = np.hypot((x + 0.5) / s - 0.84, (y + 0.5) / s - 0.84)
        inner = (d <= 0.13).astype(np.float32).reshape(px, ss, px, ss).mean(axis=(1, 3))
        outer = (d <= 0.20).astype(np.float32).reshape(px, ss, px, ss).mean(axis=(1, 3))
        ring_rgb = _rgb(dot_ring or "#000000")
        # Ausschnitt in Hintergrundfarbe, dann roter Punkt
        img[..., :3] = img[..., :3] * (1 - outer[..., None]) + ring_rgb * outer[..., None]
        img[..., 3] = np.maximum(img[..., 3], outer * 255)
        img[..., :3] = img[..., :3] * (1 - inner[..., None]) + _rgb(dot) * inner[..., None]
    return img.clip(0, 255).astype(np.uint8)


def render_icon(px, disc_color="#14513F", ring_color="#F4F1E6"):
    """Murmel-Icon: dein Ring-Logo auf grüner Scheibe (NoTime = weiß/schwarz)."""
    ss = 4
    s = px * ss
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.hypot((x + 0.5) / s * 2 - 1, (y + 0.5) / s * 2 - 1)
    disc = (r <= 0.985).astype(np.float32).reshape(px, ss, px, ss).mean(axis=(1, 3))
    rings = rings_alpha(px, scale=0.78)
    img = np.zeros((px, px, 4), np.float32)
    d, r_ = _rgb(disc_color), _rgb(ring_color)
    img[..., :3] = d * (1 - rings[..., None]) + r_ * rings[..., None]
    img[..., 3] = disc * 255
    return img.clip(0, 255).astype(np.uint8)


def png_bytes(rgba):
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[row].tobytes() for row in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def photo(tk_mod, rgba):
    return tk_mod.PhotoImage(data=base64.b64encode(png_bytes(rgba)).decode("ascii"), format="png")


def _bmp_entry(rgba):
    """Klassischer 32-bit-BMP-Eintrag (für kleine Größen zuverlässiger als PNG)."""
    sz = rgba.shape[0]
    bgra = rgba[::-1, :, [2, 1, 0, 3]].tobytes()
    mask_row = ((sz + 31) // 32) * 4
    hdr = struct.pack("<IiiHHIIiiII", 40, sz, sz * 2, 1, 32, 0, len(bgra), 0, 0, 0, 0)
    return hdr + bgra + b"\x00" * mask_row * sz


def write_ico(path):
    sizes = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 96, 128, 256)
    blobs = [png_bytes(render_icon(s)) if s >= 128 else _bmp_entry(render_icon(s)) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    for s, b in zip(sizes, blobs):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    with open(path, "wb") as f:
        f.write(out + b"".join(blobs))
