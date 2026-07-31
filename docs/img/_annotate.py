"""Draw the numbered tour callouts on the hero screenshot.

Regions are stored as FRACTIONS of the image, so the same script re-runs cleanly if the
screenshot is retaken at another window size. Order matches the caption table in the
manual/README — renumbering means editing both.
"""
from PIL import Image, ImageDraw, ImageFont

SRC = "/work/docs/img/hero-raw.png"
OUT = "/work/docs/img/hero-annotated.png"

INDIGO = (79, 70, 229)
AMBER = (217, 119, 6)
TEAL = (13, 148, 136)
WHITE = (255, 255, 255)

# n, box (x0, y0, x1, y1), badge CENTRE (x, y) — all fractions of the image.
# The badge sits OUTSIDE its box on purpose: on the inside it covers the label the
# callout is pointing at, which is the one thing the reader needs to read.
CALLOUTS = [
    (1,  (0.082, 0.034, 0.380, 0.066), (0.082, 0.014), INDIGO),  # the six tabs
    (2,  (0.641, 0.036, 0.752, 0.064), (0.752, 0.014), AMBER),   # demo-data badge
    (3,  (0.878, 0.036, 0.997, 0.064), (0.872, 0.014), TEAL),    # External / Internal
    (4,  (0.002, 0.070, 0.178, 0.101), (0.194, 0.085), INDIGO),  # Scan all / Add a job
    (5,  (0.002, 0.180, 0.243, 0.226), (0.208, 0.212), INDIGO),  # status chips
    (6,  (0.000, 0.254, 0.245, 0.302), (0.218, 0.278), INDIGO),  # the job row
    (7,  (0.350, 0.138, 0.410, 0.168), (0.350, 0.117), INDIGO),  # Evaluate fit
    (8,  (0.250, 0.350, 0.747, 0.567), (0.238, 0.360), INDIGO),  # evaluation + strengths
    (9,  (0.410, 0.138, 0.492, 0.168), (0.500, 0.117), AMBER),   # Prepare to apply (gate)
    (10, (0.750, 0.068, 0.998, 0.995), (0.772, 0.330), TEAL),    # local Claude terminal
]

img = Image.open(SRC).convert("RGBA")
W, H = img.size
wash = Image.new("RGBA", (W, H), (0, 0, 0, 0))
wd = ImageDraw.Draw(wash)
draw = ImageDraw.Draw(img)


def font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


F = font(26)
R = 23  # badge radius

for num, (fx0, fy0, fx1, fy1), (bx, by), colour in CALLOUTS:
    x0, y0 = int(fx0 * W), int(fy0 * H)
    x1, y1 = int(fx1 * W), int(fy1 * H)
    x0, y0 = max(3, x0), max(3, y0)
    x1, y1 = min(W - 4, x1), min(H - 4, y1)
    # translucent wash marks the region without hiding what's under it
    wd.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=colour + (26,))
    # white underlay so the outline survives on both pale cards and the dark terminal
    draw.rounded_rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], radius=14, outline=WHITE, width=5)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=12, outline=colour, width=3)
    cx = min(max(int(bx * W), R + 4), W - R - 4)
    cy = min(max(int(by * H), R + 4), H - R - 4)
    draw.ellipse([cx - R, cy - R, cx + R, cy + R], fill=colour, outline=WHITE, width=4)
    t = str(num)
    b = draw.textbbox((0, 0), t, font=F)
    draw.text((cx - (b[2] - b[0]) / 2, cy - (b[3] - b[1]) / 2 - 3), t, font=F, fill=WHITE)

Image.alpha_composite(img, wash).convert("RGB").save(OUT)
print(f"annotated {W}x{H} -> docs/img/hero-annotated.png ({len(CALLOUTS)} callouts)")
