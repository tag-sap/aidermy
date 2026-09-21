import os, urllib.request
from PIL import Image, ImageDraw, ImageFont

MONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
SACR_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/sacramento/Sacramento-Regular.ttf"

def download(url, path):
    if not os.path.exists(path):
        urllib.request.urlretrieve(url, path)

mont = os.path.join(os.path.dirname(__file__), "montserrat.ttf")
sacr = os.path.join(os.path.dirname(__file__), "sacramento.ttf")
download(MONT_URL, mont)
download(SACR_URL, sacr)

BG = (245, 241, 233, 255)   # #f5f1e9
INK = (23, 26, 24, 255)     # #171a18
MOSS = (64, 88, 77, 255)    # #40584d


def render(size):
    img = Image.new("RGBA", (size, size), BG)

    # rounded corners mask
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.20), fill=255)

    ai_font = ImageFont.truetype(mont, int(size * 0.31))
    try:
        ai_font.set_variation_by_axes([600])
    except Exception:
        pass
    dermy_font = ImageFont.truetype(sacr, int(size * 0.30))

    ai_text = "AI"
    dermy_text = "dermy"

    # measure
    draw = ImageDraw.Draw(img)
    ai_bbox = draw.textbbox((0, 0), ai_text, font=ai_font)
    dermy_bbox = draw.textbbox((0, 0), dermy_text, font=dermy_font)

    ai_w = ai_bbox[2] - ai_bbox[0]
    ai_h = ai_bbox[3] - ai_bbox[1]
    dermy_w = dermy_bbox[2] - dermy_bbox[0]
    dermy_h = dermy_bbox[3] - dermy_bbox[1]

    overlap = int(size * 0.04)
    total_w = ai_w + dermy_w - overlap
    x = (size - total_w) // 2

    # vertical centering: use the visual heights
    max_h = max(ai_h, dermy_h)
    top = (size - max_h) // 2

    draw.text((x - ai_bbox[0], top - ai_bbox[1]), ai_text, font=ai_font, fill=INK)
    dx = x + ai_w - overlap - dermy_bbox[0]
    draw.text((dx, top - dermy_bbox[1] + int(size * 0.01)), dermy_text, font=dermy_font, fill=MOSS)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


PUB = os.path.join(os.path.dirname(__file__), "public")
for size, name in [(512, "icon-512.png"), (192, "icon-192.png"), (180, "apple-icon.png"), (32, "favicon-32.png")]:
    img = render(size)
    path = os.path.join(PUB, name)
    img.save(path)
    print("saved", path)

# favicon.ico (multi-size)
img32 = render(32)
ico_path = os.path.join(PUB, "favicon.ico")
img32.save(ico_path, sizes=[(32, 32)])
print("saved", ico_path)


def svg_coords(size=512):
    ai_font = ImageFont.truetype(mont, int(size * 0.31))
    try:
        ai_font.set_variation_by_axes([600])
    except Exception:
        pass
    dermy_font = ImageFont.truetype(sacr, int(size * 0.30))
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    ai_bbox = d.textbbox((0, 0), "AI", font=ai_font)
    dermy_bbox = d.textbbox((0, 0), "dermy", font=dermy_font)
    ai_w = ai_bbox[2] - ai_bbox[0]
    dermy_w = dermy_bbox[2] - dermy_bbox[0]
    overlap = int(size * 0.04)
    total_w = ai_w + dermy_w - overlap
    x = (size - total_w) // 2

    ai_ascent, ai_descent = ai_font.getmetrics()
    dermy_ascent, dermy_descent = dermy_font.getmetrics()
    max_ascent = max(ai_ascent, dermy_ascent)
    max_descent = max(ai_descent, dermy_descent)
    block_h = max_ascent + max_descent
    baseline_y = (size - block_h) // 2 + max_ascent

    ai_x = x - ai_bbox[0]
    dermy_x = x + ai_w - overlap - dermy_bbox[0]
    return ai_x, baseline_y, dermy_x, baseline_y


ai_x, ai_b, dermy_x, dermy_b = svg_coords()
svg = f'''<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600&amp;family=Sacramento&amp;display=swap');
  </style>
  <rect width="512" height="512" rx="102" fill="#f5f1e9"/>
  <text x="{ai_x}" y="{ai_b}" font-family="Montserrat, sans-serif" font-weight="600" font-size="158" letter-spacing="-10" fill="#171a18">AI</text>
  <text x="{dermy_x}" y="{dermy_b}" font-family="Sacramento, cursive" font-size="153" fill="#40584d">dermy</text>
</svg>'''
with open(os.path.join(PUB, "icon.svg"), "w", encoding="utf-8") as f:
    f.write(svg)
print("saved", os.path.join(PUB, "icon.svg"))
