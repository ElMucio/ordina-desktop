"""Genera assets/app.ico: griglia di icone chiare su un quadrato blu arrotondato."""
import struct
from pathlib import Path

SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
BLUE = (0xD9, 0x6B, 0x1F)  # BGR
LIGHT = (0xFF, 0xF4, 0xE8)


def coverage(x, y, left, top, right, bottom, radius):
    """Quanta parte del pixel cade nel rettangolo arrotondato, campionando 4x4."""
    inside = 0
    for sub_y in range(4):
        for sub_x in range(4):
            px, py = x + (sub_x + 0.5) / 4, y + (sub_y + 0.5) / 4
            dx = max(left + radius - px, 0, px - (right - radius))
            dy = max(top + radius - py, 0, py - (bottom - radius))
            if left <= px <= right and top <= py <= bottom and dx * dx + dy * dy <= radius * radius:
                inside += 1
    return inside / 16


def draw(size):
    pixels = bytearray()
    cell = size * 0.2
    gap = size * 0.08
    start = (size - (3 * cell + 2 * gap)) / 2
    tiles = [(start + c * (cell + gap), start + r * (cell + gap)) for r in range(3) for c in range(3)]
    for y in range(size - 1, -1, -1):  # le DIB vanno dal basso verso l'alto
        for x in range(size):
            alpha = coverage(x, y, 0, 0, size, size, size * 0.2)
            light = max(coverage(x, y, tx, ty, tx + cell, ty + cell, cell * 0.2) for tx, ty in tiles)
            color = [round(b + (l - b) * light) for b, l in zip(BLUE, LIGHT)]
            pixels += bytes((color[0], color[1], color[2], round(alpha * 255)))
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    mask = bytes(((size + 31) // 32) * 4 * size)
    return header + bytes(pixels) + mask


def main():
    images = [draw(size) for size in SIZES]
    offset = 6 + 16 * len(images)
    directory = struct.pack("<HHH", 0, 1, len(images))
    for size, image in zip(SIZES, images):
        side = 0 if size == 256 else size
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(image), offset)
        offset += len(image)
    target = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(directory + b"".join(images))
    print(target, target.stat().st_size)


if __name__ == "__main__":
    main()
