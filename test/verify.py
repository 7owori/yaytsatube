"""Проверка собранного exe: python test/verify.py донор.exe build/Yaytsatube.exe"""
import sys, struct, zlib, marshal, hashlib, io, zipfile, types, os
sys.path.insert(0, 'tools'); import pe
from PIL import Image
MAGIC = b'MEI\014\013\012\013\016'
def read(path):
    d = open(path, 'rb').read(); p = d.rfind(MAGIC)
    _, pkglen, tocoff, toclen, pyver, pylib = struct.unpack('!8sIIII64s', d[p:p+88]); start = len(d) - pkglen
    toc = d[start+tocoff:start+tocoff+toclen]; i = 0; out = []
    while i < len(toc):
        esz, pos, csz, usz, cflag, typ = struct.unpack('!IIIIBc', toc[i:i+18]); name = toc[i+18:i+esz].rstrip(b'\0').decode()
        raw = d[start+pos:start+pos+csz]; data = zlib.decompress(raw) if cflag else raw
        assert len(data) == usz, name; out.append((name, typ, esz, data)); i += esz
    return d, start, out, (pyver, pylib)
od, ostart, old, ocookie = read(sys.argv[1])          # exe-донор с рантаймом
nd, nstart, new, ncookie = read(sys.argv[2])
ok = lambda c, m: print(('PASS ' if c else 'FAIL ') + m)
ok(ocookie == ncookie and ostart == nstart, 'загрузчик и заголовок архива те же (Python %d)' % ncookie[0])
diff = [(a[0], b[0]) for a, b in zip(old, new) if a[3] != b[3] or a[0] != b[0]]
ok(len(old) == len(new) and diff == [('gameboost', 'eggtube'), ('icon.ico', 'icon.ico'), ('ui.html', 'ui.html')], 'изменены только: %s' % diff)
ok(all(a[1] == b[1] and (a[2] == b[2] or a[0] != b[0]) for a, b in zip(old, new)), 'типы и выравнивание записей совпадают')
import subprocess
open('/tmp/egg_code.bin', 'wb').write([e for e in new if e[0] == 'eggtube'][0][3])
r = subprocess.run(['python3.12', '-I', '-c', "import marshal,types;c=marshal.loads(open('/tmp/egg_code.bin','rb').read());print(isinstance(c,types.CodeType) and 'gui' in c.co_names and c.co_filename=='eggtube.py')"], capture_output=True, text=True)
ok(r.stdout.strip() == 'True', 'программа читается как байткод 3.12')
ok([e for e in new if e[0] == 'ui.html'][0][3] == open('app/ui.html', 'rb').read(), 'ui.html внутри тот же, что проверялся')
# ресурсы
hd = nd[:nstart]; info = pe.parse(hd); rs = [s for s in info['secs'] if s['name'] == '.rsrc'][0]; res = pe.rsrc_walk(hd, rs)
sizes = []
for e in res:
    if e['path'][0] == 3:
        im = Image.open(io.BytesIO(hd[e['off']:e['off']+e['size']])); im.load(); sizes.append(im.size[0])
        r, g, b, a = im.convert('RGBA').getpixel((im.size[0]//2 - im.size[0]//6, im.size[1]//4)); assert r >= 250 and g <= 8 and b <= 8 and a >= 250, (r, g, b, a)
ok(sizes == [16, 24, 32, 48, 64, 128, 256], 'иконки в exe: %s, красные' % sizes)
g = [e for e in res if e['path'][0] == 14][0]
ok(all(struct.unpack_from('<I', hd, g['off']+6+i*14+8)[0] == [e for e in res if e['path'][:2] == [3, i+1]][0]['size'] for i in range(7)), 'таблица иконок согласована')
ok(sum(x != y for x, y in zip(od[:ostart], hd)) < 40000 and od[:rs['rptr']] == hd[:rs['rptr']] and od[rs['rptr']+rs['rsz']:ostart] == hd[rs['rptr']+rs['rsz']:], 'код загрузчика не тронут, отличается только секция ресурсов')
# все ли модули, которые тянет программа, есть в сборке
z = [e for e in new if e[0] == 'PYZ.pyz'][0][3]; pyz = marshal.loads(z[struct.unpack('!I', z[8:12])[0]:]); pyz = set(dict(pyz) if isinstance(pyz, list) else pyz)
base = {n[:-4].replace('/', '.').removesuffix('.__init__') for n in zipfile.ZipFile(io.BytesIO([e for e in new if e[0] == 'base_library.zip'][0][3])).namelist()}
ext = {e[0].split('.')[0].replace('\\', '.') for e in new if e[0].endswith('.pyd')}
import subprocess
probe = "import sys;sys.argv=['x'];import ctypes,glob,json,os,re,subprocess,threading,time,urllib.request,zipfile,pathlib,ssl,http.client;urllib.request.build_opener();print('\\n'.join(sorted(m for m in sys.modules)))"
mods = subprocess.run(['python3.12', '-I', '-c', probe], capture_output=True, text=True).stdout.split()
skip = {'os.path', 'struct', 'posix', 'posixpath', 'pwd', 'grp', 'fcntl', '_posixsubprocess', 'termios', '_posixshmem', 'resource', '_scproxy', 'sitecustomize', 'usercustomize', 'site', '_sitebuiltins', '_distutils_hack', '__main__', '_sysconfigdata__linux_x86_64-linux-gnu', '_bootlocale'}
missing = [m for m in mods if m not in pyz and m not in base and m not in ext and m not in skip and m not in sys.builtin_module_names
           and not m.startswith(('_frozen', 'zipimport', 'encodings', 'importlib', '_sysconfigdata', 'pip', 'setuptools', 'pkg_resources'))]
ok(not [m for m in missing if not m.startswith('_')], 'нужные модули есть в сборке; под вопросом: %s' % missing)
