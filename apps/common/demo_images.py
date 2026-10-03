"""Original illustrations for demo content: appliances, banners and blog covers drawn with Pillow.

No photos are downloaded (they would belong to someone else); every picture is drawn here from
simple shapes, so the demo store looks complete without copyright questions.
"""
import io
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 800

FINISHES = {
    "white": ((246, 247, 249), (214, 219, 226)),
    "silver": ((214, 219, 226), (160, 168, 180)),
    "steel": ((190, 196, 204), (120, 128, 140)),
    "black": ((70, 74, 82), (30, 32, 38)),
    "red": ((214, 70, 70), (150, 36, 40)),
    "cream": ((242, 233, 214), (210, 196, 168)),
}
BACKDROPS = [
    ((232, 244, 247), (200, 228, 235)),
    ((240, 240, 248), (214, 216, 236)),
    ((246, 241, 233), (230, 220, 202)),
    ((236, 246, 238), (208, 232, 214)),
]


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        draw.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _body(draw, box, finish, radius=28):
    light, dark = FINISHES[finish]
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=radius, fill=light, outline=dark, width=4)
    # a soft highlight down the left edge reads as a glossy panel
    draw.rounded_rectangle((x0 + 14, y0 + 14, x0 + 34, y1 - 14), radius=10, fill=tuple(min(255, c + 12) for c in light))
    return light, dark


def _shadow(img, box):
    x0, _, x1, y1 = box
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((x0 - 20, y1 - 18, x1 + 20, y1 + 26), fill=(0, 0, 0, 70))
    img.paste(layer.filter(ImageFilter.GaussianBlur(14)), (0, 0), layer.filter(ImageFilter.GaussianBlur(14)))


def _fridge(d, f):
    box = (250, 90, 550, 720)
    light, dark = _body(d, box, f)
    d.line((250, 330, 550, 330), fill=dark, width=5)
    for y0, y1 in ((150, 300), (370, 560)):
        d.rounded_rectangle((500, y0, 516, y1), radius=8, fill=dark)
    d.rounded_rectangle((300, 140, 390, 200), radius=10, outline=dark, width=3)  # display
    return box


def _side_by_side(d, f):
    box = (200, 90, 600, 720)
    light, dark = _body(d, box, f)
    d.line((400, 100, 400, 710), fill=dark, width=5)
    for x in (370, 418):
        d.rounded_rectangle((x, 220, x + 14, 520), radius=7, fill=dark)
    d.rounded_rectangle((240, 180, 340, 280), radius=12, fill=(60, 70, 80))  # water dispenser
    return box


def _washer(d, f):
    box = (210, 150, 590, 700)
    light, dark = _body(d, box, f)
    d.line((210, 250, 590, 250), fill=dark, width=4)
    d.ellipse((470, 175, 530, 235), outline=dark, width=5)
    d.rounded_rectangle((260, 190, 400, 222), radius=8, fill=(60, 70, 80))
    d.ellipse((275, 300, 525, 550), fill=dark)
    d.ellipse((300, 325, 500, 525), fill=(120, 160, 190))
    d.arc((320, 345, 480, 505), 200, 300, fill=(230, 240, 248), width=8)
    return box


def _dishwasher(d, f):
    box = (210, 160, 590, 700)
    light, dark = _body(d, box, f)
    d.rectangle((230, 180, 570, 240), fill=dark)
    for i in range(5):
        d.ellipse((260 + i * 50, 200, 280 + i * 50, 220), fill=(120, 210, 230))
    d.rounded_rectangle((300, 280, 500, 300), radius=10, fill=dark)
    return box


def _stove(d, f):
    box = (150, 330, 650, 560)
    light, dark = _body(d, box, f, radius=22)
    d.rounded_rectangle((150, 330, 650, 380), radius=20, fill=(40, 44, 52))
    for cx in (260, 400, 540):
        d.ellipse((cx - 60, 250, cx + 60, 330), fill=(50, 54, 62))
        d.ellipse((cx - 30, 270, cx + 30, 310), fill=(90, 96, 106))
        for k in range(8):
            a = k * math.pi / 4
            d.line((cx, 290, cx + 55 * math.cos(a), 290 + 30 * math.sin(a)), fill=(150, 150, 150), width=4)
    for cx in (230, 330, 470, 570):
        d.ellipse((cx - 22, 420, cx + 22, 464), fill=dark)
    return box


def _vacuum(d, f):
    box = (230, 380, 560, 640)
    light, dark = _body(d, box, f, radius=120)
    d.arc((420, 150, 700, 520), 180, 300, fill=(60, 64, 72), width=22)
    d.rounded_rectangle((600, 560, 700, 600), radius=12, fill=(60, 64, 72))
    for cx in (290, 500):
        d.ellipse((cx - 38, 600, cx + 38, 676), fill=(40, 44, 52))
    d.ellipse((350, 440, 440, 530), fill=dark)
    return box


def _airfryer(d, f):
    box = (250, 180, 550, 680)
    light, dark = _body(d, box, f, radius=70)
    d.rounded_rectangle((280, 420, 520, 640), radius=30, fill=dark)
    d.rounded_rectangle((360, 500, 440, 530), radius=12, fill=light)
    d.ellipse((350, 240, 450, 340), outline=dark, width=6)
    return box


def _microwave(d, f):
    box = (130, 260, 670, 600)
    light, dark = _body(d, box, f, radius=24)
    d.rounded_rectangle((165, 295, 520, 565), radius=16, fill=(40, 46, 56))
    d.rounded_rectangle((185, 315, 500, 545), radius=12, fill=(70, 86, 100))
    for i in range(4):
        d.rounded_rectangle((560, 310 + i * 55, 640, 345 + i * 55), radius=8, fill=dark)
    return box


def _coffee(d, f):
    box = (260, 160, 540, 680)
    light, dark = _body(d, box, f, radius=30)
    d.rectangle((300, 380, 500, 600), fill=(40, 44, 52))
    d.rounded_rectangle((350, 470, 450, 590), radius=14, fill=(250, 250, 250))
    d.ellipse((365, 480, 435, 500), fill=(110, 70, 40))
    d.rounded_rectangle((330, 210, 470, 260), radius=10, fill=dark)
    return box


def _tv(d, f):
    box = (90, 190, 710, 560)
    d.rounded_rectangle(box, radius=14, fill=(24, 26, 30))
    screen = _gradient((580, 330), (40, 110, 160), (120, 60, 160))
    d._image.paste(screen, (110, 210))
    d.polygon([(330, 560), (470, 560), (500, 640), (300, 640)], fill=(40, 44, 52))
    return (300, 560, 500, 640)


def _ac(d, f):
    box = (110, 260, 690, 470)
    light, dark = _body(d, box, f, radius=40)
    for i in range(6):
        d.line((160, 420 + i * 8, 640, 420 + i * 8), fill=dark, width=3)
    d.rounded_rectangle((560, 300, 640, 340), radius=10, fill=(60, 70, 80))
    for i in range(3):
        d.arc((250 + i * 110, 470, 330 + i * 110, 600), 60, 120, fill=(150, 200, 230), width=6)
    return box


SHAPES = {
    "fridge": _fridge, "side_by_side": _side_by_side, "washer": _washer, "dishwasher": _dishwasher,
    "stove": _stove, "vacuum": _vacuum, "airfryer": _airfryer, "microwave": _microwave,
    "coffee": _coffee, "tv": _tv, "ac": _ac,
}


def _jpeg(img, quality=86) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue()


def product_image(shape: str, finish: str = "white", label: str = "", backdrop: int = 0, zoom: float = 1.0) -> bytes:
    """A square product picture; `zoom` > 1 crops in for a «detail» gallery shot."""
    img = _gradient((SIZE, SIZE), *BACKDROPS[backdrop % len(BACKDROPS)])
    draw = ImageDraw.Draw(img)
    draw._image = img
    box = SHAPES[shape](draw, finish)
    _shadow(img, box)
    draw = ImageDraw.Draw(img)
    draw._image = img
    SHAPES[shape](draw, finish)  # redraw on top of the shadow
    if label:
        draw.text((SIZE // 2, 760), label, fill=(90, 100, 112), font=_font(30), anchor="mm")
    if zoom > 1:
        w = int(SIZE / zoom)
        left = (SIZE - w) // 2
        img = img.crop((left, left - 40, left + w, left + w - 40)).resize((SIZE, SIZE), Image.LANCZOS)
    return _jpeg(img)


def banner_image(top, bottom, shapes, finish="white") -> bytes:
    """A wide banner: colour wash plus a row of appliances on the left (text is laid over by the page)."""
    w, h = 1400, 560
    img = _gradient((w, h), top, bottom)
    draw = ImageDraw.Draw(img)
    for i in range(14):
        draw.ellipse((900 + i * 37 % 300, -80 + i * 53 % 500, 1040 + i * 37 % 300, 60 + i * 53 % 500),
                     outline=tuple(min(255, c + 30) for c in top), width=2)
    for i, shape in enumerate(shapes):
        tile = Image.open(io.BytesIO(product_image(shape, finish, backdrop=i))).resize((360, 360))
        mask = Image.new("L", tile.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 359, 359), radius=36, fill=255)
        img.paste(tile, (60 + i * 300, 120 + (i % 2) * 40), mask)
    return _jpeg(img, 84)


def cover_image(shape, top, bottom) -> bytes:
    """A 16:9 blog cover."""
    img = _gradient((1200, 675), top, bottom)
    tile = Image.open(io.BytesIO(product_image(shape, "white", backdrop=1))).resize((520, 520))
    mask = Image.new("L", tile.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 519, 519), fill=255)
    img.paste(tile, (340, 78), mask)
    return _jpeg(img, 84)
