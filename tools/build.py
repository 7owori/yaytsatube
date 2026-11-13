"""Собирает Yaytsatube.exe: берёт готовый Windows-рантайм (Python 3.12 + pywebview) из Яйцечиста,
меняет иконку в ресурсах exe и кладёт в архив PyInstaller свою программу и интерфейс."""
import marshal, struct, sys, zlib
sys.path.insert(0, 'tools'); import pe
assert sys.version_info[:2] == (3, 12), 'байткод должен быть от Python 3.12'
SRC, OUT = sys.argv[1], sys.argv[2]
d = bytearray(open(SRC, 'rb').read())
MAGIC = b'MEI\014\013\012\013\016'
p = d.rfind(MAGIC); assert p + 88 == len(d)
magic, pkglen, tocoff, toclen, pyver, pylib = struct.unpack('!8sIIII64s', d[p:p+88])
start = len(d) - pkglen
head = d[:start]

# 1. иконка: новые PNG в те же места ресурсов (они меньше старых), размеры поправить в таблицах
info = pe.parse(head); rs = [s for s in info['secs'] if s['name'] == '.rsrc'][0]
res = pe.rsrc_walk(head, rs)
ico = open('build/icon.ico', 'rb').read(); n = struct.unpack_from('<H', ico, 4)[0]
imgs = {}
for i in range(n):
    w, h, _, _, _, _, size, off = struct.unpack_from('<BBBBHHII', ico, 6 + i*16); imgs[w] = ico[off:off+size]
grp = [e for e in res if e['path'][0] == 14][0]
for i in range(struct.unpack_from('<H', head, grp['off'] + 4)[0]):
    eo = grp['off'] + 6 + i*14
    w, h, _, _, _, _, size, rid = struct.unpack_from('<BBBBHHIH', head, eo)
    slot = [e for e in res if e['path'][:2] == [3, rid]][0]
    new = imgs[w]; assert len(new) <= slot['size'], (w, len(new), slot['size'])
    head[slot['off']:slot['off'] + slot['size']] = new + bytes(slot['size'] - len(new))
    struct.pack_into('<I', head, slot['entry'] + 4, len(new))
    struct.pack_into('<I', head, eo + 8, len(new))

# 2. архив: всё как было, кроме программы, интерфейса и иконки
toc = bytes(d[start + tocoff:start + tocoff + toclen]); entries = []; i = 0
while i < len(toc):
    esz, pos, csz, usz, cflag, typ = struct.unpack('!IIIIBc', toc[i:i+18])
    name = toc[i+18:i+esz].rstrip(b'\0').decode(); i += esz
    entries.append([name, bytes(d[start+pos:start+pos+csz]), usz, cflag, typ])
code = marshal.dumps(compile(open('app/eggtube.py', encoding='utf8').read(), 'eggtube.py', 'exec'))
swap = {'gameboost': ('eggtube', code), 'ui.html': ('ui.html', open('app/ui.html', 'rb').read()), 'icon.ico': ('icon.ico', ico)}
done = set()
for e in entries:
    if e[0] in swap:
        name, raw = swap[e[0]]; done.add(e[0])
        e[0], e[1], e[2] = name, (zlib.compress(raw, 9) if e[3] else raw), len(raw)
assert done == set(swap), done
body = bytearray(); newtoc = bytearray()
for name, blob, usz, cflag, typ in entries:
    nb = name.encode() + b'\0'; esz = 18 + len(nb); pad = (16 - esz % 16) % 16
    newtoc += struct.pack('!IIIIBc', esz + pad, len(body), len(blob), usz, cflag, typ) + nb + bytes(pad)
    body += blob
cookie = struct.pack('!8sIIII64s', MAGIC, len(body) + len(newtoc) + 88, len(body), len(newtoc), pyver, pylib)
open(OUT, 'wb').write(head + body + newtoc + cookie)
print('ok', OUT, len(head) + len(body) + len(newtoc) + 88, 'bytes;', len(entries), 'entries')
