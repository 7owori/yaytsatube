import io, struct, sys
from PIL import Image, ImageDraw
def bez(p0, p1, p2, p3, n=60):
    return [tuple((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t*t*c + t**3*d for a, b, c, d in zip(p0, p1, p2, p3)) for t in (i/n for i in range(n+1))]
EGG = bez((30,2),(45,2),(56,28),(56,46)) + bez((56,46),(56,62),(44,74),(30,74)) + bez((30,74),(16,74),(4,62),(4,46)) + bez((4,46),(4,28),(15,2),(30,2))
TRI = [(24.5,28.5),(41,39),(24.5,49.5)]
def render(size, S=8):
    W = size*S
    k = W/80.0; ox = (W - 60*k)/2; oy = (W - 76*k)/2
    T = lambda pts: [(ox + x*k, oy + y*k) for x, y in pts]
    im = Image.new('RGBA', (W, W), (0,0,0,0)); d = ImageDraw.Draw(im)
    d.polygon(T(EGG), fill=(255,0,0,255))
    t = T(TRI); r = 3.5*k
    d.polygon(t, fill=(255,255,255,255))
    d.line(t + [t[0], t[1]], fill=(255,255,255,255), width=int(7*k), joint='curve')
    for x, y in t: d.ellipse((x-r, y-r, x+r, y+r), fill=(255,255,255,255))
    return im.resize((size, size), Image.LANCZOS)
def png(im, limit=None):
    b = io.BytesIO(); im.save(b, 'PNG', optimize=True); out = b.getvalue()
    colors = 256
    while limit and len(out) > limit and colors >= 8:
        q = im.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        b = io.BytesIO(); q.save(b, 'PNG', optimize=True); out = b.getvalue(); colors //= 2
    return out
if __name__ == '__main__':
    out = sys.argv[1]
    sizes = [16, 24, 32, 48, 64, 128, 256]
    data = [png(render(s)) for s in sizes]
    hdr = struct.pack('<HHH', 0, 1, len(sizes)); off = 6 + 16*len(sizes); body = b''
    for s, d in zip(sizes, data):
        hdr += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(d), off + len(body)); body += d
    open(out + '/icon.ico', 'wb').write(hdr + body)
    render(256).save(out + '/icon256.png'); render(48).resize((192,192), Image.NEAREST).save(out + '/icon48x4.png')
    print([len(d) for d in data])
