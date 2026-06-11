import struct
from pathlib import Path
from PIL import Image, ImageDraw


SIZES = [16, 32, 48, 64, 128, 256]
ICO_PATH = Path(__file__).parent / "icon.ico"


def _rounded_rect(draw, xy, r, fill):
    x1, y1, x2, y2 = xy
    draw.pieslice([x1, y1, x1 + r * 2, y1 + r * 2], 180, 270, fill=fill)
    draw.pieslice([x2 - r * 2, y1, x2, y1 + r * 2], 270, 360, fill=fill)
    draw.pieslice([x1, y2 - r * 2, x1 + r * 2, y2], 90, 180, fill=fill)
    draw.pieslice([x2 - r * 2, y2 - r * 2, x2, y2], 0, 90, fill=fill)
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)


def _draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    r = s / 256

    pad = int(6 * r)
    _rounded_rect(draw, (pad, pad, s - pad, s - pad), int(16 * r), "#06B6D4")

    doc_m = int(36 * r)
    doc_w = s - doc_m * 2
    doc_h = int(180 * r)
    doc_y = int(40 * r)
    _rounded_rect(draw, (doc_m, doc_y, doc_m + doc_w, doc_y + doc_h), int(12 * r), "white")

    fold_w, fold_h = int(32 * r), int(40 * r)
    draw.polygon([
        (doc_m + doc_w - fold_w, doc_y),
        (doc_m + doc_w, doc_y + fold_h),
        (doc_m + doc_w, doc_y),
    ], fill="#E2E8F0")

    line_colors = ["#CBD5E1", "#CBD5E1", "#CBD5E1", "#CBD5E1"]
    line_ys = [int(90 * r), int(118 * r), int(146 * r), int(174 * r)]
    line_lengths = [int(100 * r), int(86 * r), int(68 * r), int(50 * r)]
    line_x = doc_m + int(20 * r)
    for i, ly in enumerate(line_ys):
        lw = max(2, int(4 * r))
        draw.rounded_rectangle(
            [line_x, ly, line_x + line_lengths[i], ly + lw],
            radius=int(2 * r), fill=line_colors[i]
        )

    cx = doc_m + int(88 * r)
    cy = doc_y + int(60 * r)
    cr = int(22 * r)
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill="#06B6D4")

    if size >= 32:
        b_w = int(14 * r)
        b_h = int(28 * r)
        b_x = cx - int(8 * r)
        b_y = cy - int(14 * r)
        draw.rectangle([b_x, b_y, b_x + int(4 * r), b_y + b_h], fill="white")
        draw.rectangle([b_x + int(4 * r), b_y, b_x + b_w, b_y + int(11 * r)], fill="white")
        draw.rectangle([b_x + int(4 * r), b_y + int(17 * r), b_x + b_w, b_y + b_h], fill="white")
        draw.rectangle([b_x + int(4 * r), b_y + int(11 * r), b_x + b_w - int(2 * r), b_y + int(17 * r)], fill="white")

    return img


def _rgba_to_bmp_bytes(im):
    """Convert RGBA PIL image to BMP DIBS section bytes (BGRA, bottom-up)."""
    w, h = im.size
    # BMP stores rows bottom-up
    raw = im.tobytes()  # RGBA
    pixels = bytearray()
    for y in range(h - 1, -1, -1):
        row = raw[y * w * 4 : (y + 1) * w * 4]
        # RGBA → BGRA
        for i in range(0, len(row), 4):
            pixels.extend([row[i + 2], row[i + 1], row[i], row[i + 3]])
        # row padding to 4-byte boundary
        pad = (4 - (w * 4) % 4) % 4
        pixels.extend(b"\x00" * pad)
    return bytes(pixels)


def _make_ico_data(images):
    """Build a complete .ico file from a list of PIL RGBA images."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)

    # Collect each image's BMP data
    bmp_data_list = []
    total_data_offset = 6 + count * 16

    for im in images:
        w, h = im.size
        bmp = _rgba_to_bmp_bytes(im)
        # BITMAPINFOHEADER
        bih = struct.pack(
            "<IiiHHIIiiII",
            40,              # biSize
            w,               # biWidth
            h * 2,           # biHeight (doubled for ICO)
            1,               # biPlanes
            32,              # biBitCount
            0,               # biCompression (BI_RGB)
            len(bmp),        # biSizeImage
            0, 0, 0, 0,      # biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant
        )
        bmp_data_list.append(bih + bmp)

    # Directory entries
    dir_entries = b""
    offset = total_data_offset
    for i, im in enumerate(images):
        w, h = im.size
        data_size = len(bmp_data_list[i])
        # ICO directory entry: w, h, colors, reserved, planes, bpp, size, offset
        entry = struct.pack(
            "<BBBBHHII",
            w if w < 256 else 0,
            h if h < 256 else 0,
            0,       # colors
            0,       # reserved
            1,       # planes
            32,      # bpp
            data_size,
            offset,
        )
        dir_entries += entry
        offset += data_size

    # Combine
    return header + dir_entries + b"".join(bmp_data_list)


def main():
    images = []
    for size in SIZES:
        img = _draw_icon(size)
        images.append(img)

    ico_data = _make_ico_data(images)
    ICO_PATH.write_bytes(ico_data)
    print(f"OK: {ICO_PATH} ({len(ico_data)} bytes, {len(images)} sizes: {SIZES})")


if __name__ == "__main__":
    main()
