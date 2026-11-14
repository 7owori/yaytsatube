"""Яйцатюб: окно на pywebview, качает yt-dlp. Один exe, компоненты докачиваются при первом запуске."""
import base64
import ctypes
import glob
import html
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

VERSION = '4.0.0'     # служебный номер для обновления: только растёт. Людям показывается SHOWN
SHOWN = '1.1'
TITLE = 'Яйцатюб'
WIN = os.name == 'nt'
FROZEN = getattr(sys, 'frozen', False)
UPDATED = bool(globals().get('UPDATED'))   # этот код не из exe, а из папки обновления (см. run_update)
ASSETS = Path(__file__).parent if UPDATED else Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
HOME = Path(os.environ.get('EGGTUBE_HOME') or Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'EggTube')
STATE = HOME / 'state.json'
BIN = HOME / 'bin'
UPD = HOME / 'update'                 # свежий код программы, скачанный с GitHub кнопкой «Проверить обновления»
REPO = '7owori/yaytsatube'
SOURCES = (f'https://raw.githubusercontent.com/{REPO}/main/', f'https://cdn.jsdelivr.net/gh/{REPO}@main/')
LOG = HOME / 'last.log'
PREV_DIR = HOME / 'preview'
PREV_CUTS = ('*30-60', '*0-30')   # отрывок для прослушивания: с 30-й секунды, а у коротких роликов с начала
NOWIN = 0x08000000 if WIN else 0
EXE = '.exe' if WIN else ''
YTDLP = os.environ.get('EGGTUBE_YTDLP')  # только для проверок: подставной загрузчик

GH = 'https://github.com/'
TOOLS = (
    {'id': 'yt-dlp', 'need': ['yt-dlp.exe'], 'url': GH + 'yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'},
    {'id': 'ffmpeg', 'need': ['ffmpeg.exe', 'ffprobe.exe'],
     'url': GH + 'yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'},
    {'id': 'deno', 'need': ['deno.exe'],
     'url': GH + 'denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip'},
)
FRESH_DAYS = 5        # yt-dlp старше этого перекачивается сам: YouTube часто ломает старые версии
QUALITIES = ('max', '2160', '1440', '1080', '720', '480')
BROWSERS = ('', 'firefox', 'chrome', 'edge')
# кодек видео -> (что предпочесть при выборе дорожек, формат файла, чем перекодировать, если сайт такого не дал)
VCODECS = {
    'h264': ('vcodec:h264,acodec:m4a', 'mp4', None),
    'h265': ('vcodec:h265,acodec:m4a', 'mp4', ['-c:v', 'libx265', '-crf', '23', '-preset', 'medium', '-pix_fmt', 'yuv420p', '-tag:v', 'hvc1']),
    'av1': ('vcodec:av01,acodec:m4a', 'mp4', None),
    'vp9': ('vcodec:vp9,acodec:opus', 'webm', None),
    'prores': ('', 'mov', ['-c:v', 'prores_ks', '-profile:v', '2', '-pix_fmt', 'yuv422p10le', '-vendor', 'apl0']),
}
VCODEC_HAVE = {'h265': r'^(hev|hvc|h265|hevc)', 'prores': r'^(prores|ap[c4])'}   # как сайт называет уже готовую дорожку
VCODEC_NAME = {'h265': 'H.265', 'prores': 'ProRes'}
VCODEC_OLD = {'auto': 'h264'}   # настройки прошлых версий: 'vp9-webm' -> 'vp9', 'auto-mkv' -> 'h264'
ACODECS = {'mp3': ['-c:a', 'libmp3lame', '-q:a', '0'], 'm4a': ['-c:a', 'aac', '-b:a', '256k'],          # чем кодировать звук в ffmpeg
           'opus': ['-c:a', 'libopus', '-b:a', '160k'], 'flac': ['-c:a', 'flac'], 'wav': ['-c:a', 'pcm_s16le']}
FFMPEG = os.environ.get('EGGTUBE_FFMPEG')   # только для проверок
SIZES = {'wide': (1040, 720), 'tall': (520, 860)}      # форма окна: горизонтальная или вертикальная
# тема -> фон окна и цвета заголовка Windows (тёмный режим, рамка, шапка, текст; цвета в порядке BGR)
THEMES = {'dark': ('#191919', ((20, 1), (34, 0x202020), (35, 0x202020), (36, 0xD4D4D4))),
          'light': ('#F7F6F3', ((20, 0), (34, 0xDDE2E4), (35, 0xF3F6F7), (36, 0x2D2F2F)))}
EQ_BANDS = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)   # полосы эквалайзера, Гц
EQ_MAX = 12
PT_TYPES = {'bell': 'equalizer', 'ls': 'lowshelf', 'hs': 'highshelf', 'hp': 'highpass', 'lp': 'lowpass'}  # точка графика -> фильтр ffmpeg
PT_MAX, PT_GAIN, PT_F, PT_Q = 12, 18, (20, 20000), (0.3, 8)
PT_SOFT = 1.5        # полкам узкая добротность не нужна: даёт горб рядом с частотой
CUT_FLAT, CUT_Q, CUT_STEPS = 0.71, (0.5, 3.0), 4   # срез: ровный склон при 0.71; крутизна 12, 24, 36 или 48 дБ/окт
FS = 48000
DEFAULTS = {'dir': '', 'kind': 'video', 'quality': '1080', 'vcodec': 'h264', 'aformat': 'mp3', 'theme': 'dark', 'lang': 'ru', 'layout': 'wide', 'size': None, 'tray': True, 'tray_told': False, 'seen': '', 'net_mode': '', 'clip': True, 'proxy': '', 'cookies': '',
            'history': [], 'lnk': '', 'eq': [0] * 10, 'eq_mode': 'bands', 'eq_points': []}
HISTORY_MAX = 40

LOCK = threading.RLock()
JOBS = []
WAKE = threading.Event()
UPDATE = {'state': 'idle', 'ver': '', 'error': ''}   # idle | check | fresh | found | load | error
RESTART = {'on': False, 'quit': None}
TOOL = {'busy': False, 'step': '', 'done': 0, 'total': 0, 'error': '', 'ver': ''}
SEQ = [0]
INFO = {'status': 'idle', 'url': '', 'title': '', 'thumb': '', 'author': '', 'dur': None, 'error': '', 'proc': None, 'n': 0}
PREV = {'status': 'idle', 'stage': 'find', 'url': '', 'title': '', 'error': '', 'proc': None, 'n': 0}


# ---------- настройки ----------
def load():
    try:
        st = dict(DEFAULTS, **json.loads(STATE.read_text('utf-8-sig')))
    except (OSError, ValueError):
        st = dict(DEFAULTS)
    if not isinstance(st.get('history'), list):
        st['history'] = []
    st['eq'] = clean_eq(st.get('eq')) or [0] * len(EQ_BANDS)
    st['eq_points'] = clean_points(st.get('eq_points')) or []
    if st.get('eq_mode') not in ('bands', 'graph'):
        st['eq_mode'] = 'bands'
    old = str(st.get('vcodec') or '').split('-')[0]
    st['vcodec'] = VCODEC_OLD.get(old, old)
    if st['vcodec'] not in VCODECS:
        st['vcodec'] = 'h264'
    if st.get('aformat') not in ACODECS:
        st['aformat'] = 'mp3'
    if st.get('theme') not in THEMES:
        st['theme'] = 'dark'
    if st.get('lang') not in ('ru', 'en'):
        st['lang'] = 'ru'
    if st.get('layout') not in SIZES:
        st['layout'] = 'wide'
    sz = st.get('size')
    if not (isinstance(sz, list) and len(sz) == 2 and all(isinstance(x, int) and 300 <= x <= 10000 for x in sz)):
        st['size'] = None
    return st


def clean_eq(v):
    """Десять усилений в дБ, каждое от -12 до 12; иначе None."""
    if not isinstance(v, list) or len(v) != len(EQ_BANDS):
        return None
    try:
        return [max(-EQ_MAX, min(EQ_MAX, int(round(float(x))))) for x in v]
    except (TypeError, ValueError):
        return None


def eq_filter(eq):
    """Цепочка фильтров ffmpeg. Если что-то поднято, общая громкость опускается на столько же, чтобы звук не хрипел."""
    parts = [f'equalizer=f={f}:t=o:w=1:g={g}' for f, g in zip(EQ_BANDS, eq) if g]
    if not parts:
        return ''
    up = max(eq)
    return ','.join(([f'volume=-{up}dB'] if up > 0 else []) + parts)


def clean_points(v):
    """Точки графика: тип, частота, усиление, добротность, крутизна среза. Всё зажато в пределы; иначе None."""
    if not isinstance(v, list) or len(v) > PT_MAX:
        return None
    out = []
    try:
        for p in v:
            t = p['t']
            if t not in PT_TYPES:
                return None
            cut = t in ('hp', 'lp')
            lo, hi = PT_Q if t == 'bell' else CUT_Q if cut else (PT_Q[0], PT_SOFT)
            out.append({'t': t, 'f': round(max(PT_F[0], min(PT_F[1], float(p['f']))), 1),
                        'g': 0.0 if cut else round(max(-PT_GAIN, min(PT_GAIN, float(p['g']))), 1),
                        'q': round(max(lo, min(hi, float(p['q']))), 2),
                        's': max(1, min(CUT_STEPS, int(p.get('s', 1)))) if cut else 1})
    except (TypeError, ValueError, KeyError):
        return None
    return sorted(out, key=lambda p: p['f'])


def stages(p):
    """Срез — цепочка из s звеньев по 12 дБ/окт с добротностями Баттерворта: склон ровный, без горба.
    Подъём у частоты среза (q выше 0.71) достаётся только самому острому звену."""
    if p['t'] not in ('hp', 'lp'):
        return [p['q']]
    n = p['s']
    qs = sorted(1 / (2 * math.cos(math.pi * (2 * k + 1) / (4 * n))) for k in range(n))
    qs[-1] *= p['q'] / CUT_FLAT
    return qs


def biquad_db(t, f0, g, q, f):
    """Сколько дБ даёт одно звено на частоте f. Те же формулы, что у фильтров ffmpeg и у графика в окне."""
    w0 = 2 * math.pi * f0 / FS
    cw, al, A = math.cos(w0), math.sin(w0) / (2 * q), 10 ** (g / 40)
    if t == 'bell':
        b, a = (1 + al * A, -2 * cw, 1 - al * A), (1 + al / A, -2 * cw, 1 - al / A)
    elif t == 'ls':
        s = 2 * math.sqrt(A) * al
        b = (A * ((A + 1) - (A - 1) * cw + s), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - s))
        a = ((A + 1) + (A - 1) * cw + s, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - s)
    elif t == 'hs':
        s = 2 * math.sqrt(A) * al
        b = (A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s))
        a = ((A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s)
    elif t == 'hp':
        b, a = ((1 + cw) / 2, -(1 + cw), (1 + cw) / 2), (1 + al, -2 * cw, 1 - al)
    else:
        b, a = ((1 - cw) / 2, 1 - cw, (1 - cw) / 2), (1 + al, -2 * cw, 1 - al)
    w = 2 * math.pi * f / FS
    c1, c2, s1, s2 = math.cos(w), math.cos(2 * w), math.sin(w), math.sin(2 * w)
    num = (b[0] + b[1] * c1 + b[2] * c2) ** 2 + (b[1] * s1 + b[2] * s2) ** 2
    den = (a[0] + a[1] * c1 + a[2] * c2) ** 2 + (a[1] * s1 + a[2] * s2) ** 2
    return 10 * math.log10(max(num, 1e-30) / den)


def point_db(p, f):
    return sum(biquad_db(p['t'], p['f'], p['g'], q, f) for q in stages(p))


def live_points(points):
    return [p for p in points if p['t'] in ('hp', 'lp') or p['g']]


def graph_filter(points):
    points = live_points(points)
    if not points:
        return ''
    parts = []
    for p in points:
        for q in stages(p):
            s = f"{PT_TYPES[p['t']]}=f={p['f']:g}:t=q:w={q:.4g}"
            parts.append(s if p['t'] in ('hp', 'lp') else s + f":g={p['g']:g}")
    grid = [20 * 1000 ** (i / 239) for i in range(240)]
    peak = max(sum(point_db(p, f) for p in points) for f in grid)
    pre = [f'volume=-{math.ceil(peak * 10) / 10:g}dB'] if peak > 0.05 else []   # чтобы подъём не уводил звук в хрип
    return ','.join(pre + parts)


def eq_chain(st):
    return graph_filter(st['eq_points']) if st['eq_mode'] == 'graph' else eq_filter(st['eq'])


def save(st):
    with LOCK:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix('.tmp')
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), 'utf-8')
        os.replace(tmp, STATE)


def out_dir(st):
    return Path(st.get('dir') or Path.home() / 'Downloads' / 'Яйцатюб')


# ---------- компоненты ----------
def tool(name):
    return BIN / name


def own(name):
    p = tool(name)
    return p.is_file() and p.stat().st_size > 100000


def tool_path(name):
    """Где лежит компонент: сначала свой, скачанный программой, потом установленный в системе (PATH)."""
    return str(tool(name)) if own(name) else shutil.which(name)


def have(t):
    return all(tool_path(n) for n in t['need'])


def tools_view():
    with LOCK:
        v = dict(TOOL)
    v['have'] = {t['id']: have(t) for t in TOOLS}
    v['system'] = [t['id'] for t in TOOLS if have(t) and not all(own(n) for n in t['need'])]   # взяты из системы
    v['ready'] = bool(YTDLP) or v['have']['yt-dlp']
    return v


def curl(url, part, proxy='', agent=''):
    r = subprocess.run(['curl.exe', '-L', '--fail', '--silent', '--show-error', '--retry', '2', '--connect-timeout', '20']
                       + (['-x', proxy] if proxy else []) + (['-A', agent, '--compressed'] if agent else []) + ['-o', str(part), url],
                       capture_output=True, stdin=subprocess.DEVNULL, creationflags=NOWIN)
    if r.returncode:
        raise OSError('curl: ' + (r.stderr.decode('utf-8', 'replace').strip()[-200:] or f'код {r.returncode}'))


def fetch(url, dest, label, agent=''):
    """Качает файл с прогрессом. Если в настройках указан прокси, идёт через него (curl умеет и socks).
    Если Python не смог (сертификаты, блокировка) — пробует curl из Windows."""
    part = dest.with_name(dest.name + '.part')
    proxy = load().get('proxy') or ''
    with LOCK:
        TOOL.update(step=label, done=0, total=0)
    if WIN and proxy:
        try:
            curl(url, part, proxy, agent)
            return os.replace(part, dest)
        except OSError:
            pass                              # прокси не помог: пробуем напрямую
    try:
        req = urllib.request.Request(url, headers={'User-Agent': agent or 'EggTube/' + VERSION})
        with urllib.request.urlopen(req, timeout=40) as r, open(part, 'wb') as f:
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = r.read(1 << 17)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                with LOCK:
                    TOOL.update(done=done, total=total)
        if total and done != total:
            raise OSError('файл скачан не целиком')
    except Exception as first:
        if not WIN:
            raise
        try:
            curl(url, part, '', agent)
        except OSError as second:
            raise OSError(f'{type(first).__name__}: {first}; {second}')
    os.replace(part, dest)


def install_tool(t):
    BIN.mkdir(parents=True, exist_ok=True)
    if not t['url'].endswith('.zip'):
        fresh = tool(t['need'][0] + '.new')
        fetch(t['url'], fresh, t['id'])
        if fresh.stat().st_size < 1000000:
            fresh.unlink()
            raise OSError('пришёл не тот файл')
        os.replace(fresh, tool(t['need'][0]))
        return
    arc = BIN / (t['id'] + '.zip')
    fetch(t['url'], arc, t['id'])
    with LOCK:
        TOOL.update(step=t['id'] + ': распаковка', done=0, total=0)
    try:
        with zipfile.ZipFile(arc) as z:
            for info in z.infolist():
                base = info.filename.replace('\\', '/').rsplit('/', 1)[-1]
                if base in t['need']:
                    tmp = tool(base + '.new')
                    with z.open(info) as src, open(tmp, 'wb') as dst:
                        while True:
                            chunk = src.read(1 << 20)
                            if not chunk:
                                break
                            dst.write(chunk)
                    os.replace(tmp, tool(base))
    finally:
        arc.unlink(missing_ok=True)
    if not have(t):
        raise OSError('в архиве нет нужных файлов')


# ---------- Spotify ----------
# Spotify отдаёт музыку только с защитой (DRM), сам звук оттуда взять нельзя. Поэтому со страницы трека берём
# исполнителя и название, а запись ищем на YouTube и качаем оттуда.
SPOT = {}
PICK = {}
GUI = {'on': False}
BROWSE = threading.Lock()
SPOT_PIC = r'https://(?:i\.scdn\.co|[\w.-]+\.spotifycdn\.com)/image/\w+'      # обложки лежат на разных адресах
BROWSER = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
SPOT_ONLY = 'Со Spotify качаются только отдельные треки: вставь ссылку на трек, а не на альбом или плейлист.'
SPOT_FAIL = 'Не получилось узнать, что это за трек: Spotify не отдаёт данные по твоему адресу. Включи VPN на весь компьютер или укажи прокси в настройках.'


class Plain(Exception):
    """Ошибка, текст которой показываем человеку как есть."""


def is_spotify(url):
    return bool(re.match(r'https?://([\w-]+\.)*spotify\.(com|link)/', url or '', re.I))


def web_text(url, way=''):
    """Текст страницы. way='curl' — сразу через curl из Windows: у него другое соединение, чем у Python,
    и там, где одному сайт отдаёт заглушку или рвёт связь, второй проходит."""
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = HOME / f'page{threading.get_ident()}.tmp'
    try:
        if way == 'curl':
            proxy = load().get('proxy') or ''
            try:
                curl(url, tmp, proxy, BROWSER)
            except OSError:
                if not proxy:
                    raise
                curl(url, tmp, '', BROWSER)
        else:
            fetch(url, tmp, '', BROWSER)
        return tmp.read_text('utf-8', 'replace')
    finally:
        for f in (tmp, tmp.with_name(tmp.name + '.part')):
            try:
                f.unlink()
            except OSError:
                pass


def browser_text(url, script, wait=15):
    """Открывает адрес в невидимом окне программы и возвращает то, что вернул script. Окно — настоящий браузер,
    поэтому сайт отдаёт ему ту же страницу, что и человеку (простому запросу Spotify отдаёт заглушку)."""
    import webview
    with BROWSE:
        loaded = threading.Event()
        w = webview.create_window('spotify', url, hidden=True, width=480, height=320)
        try:
            w.events.loaded += lambda *a: loaded.set()
            loaded.wait(wait)
            for _ in range(16):
                got = w.evaluate_js(script)
                if got:
                    return str(got)
                time.sleep(.4)
            return ''
        finally:
            try:
                w.destroy()
            except Exception:
                pass


def spotify_entity(node):
    """В данных страницы ищет запись трека: у неё есть название и список исполнителей."""
    if isinstance(node, dict):
        names = [a.get('name') for a in node.get('artists') or [] if isinstance(a, dict)] if isinstance(node.get('artists'), list) else []
        if isinstance(node.get('name'), str) and names and all(isinstance(n, str) for n in names):
            return node
        node = list(node.values())
    if isinstance(node, list):
        for x in node:
            found = spotify_entity(x)
            if found:
                return found
    return None


def spotify_cover(data, text):
    """Самая большая обложка из данных страницы (их там несколько размеров)."""
    best = [0, '']
    def walk(node):
        if isinstance(node, dict):
            u = node.get('url')
            if isinstance(u, str) and re.match(SPOT_PIC, u):
                size = max([x for x in (node.get('maxHeight'), node.get('height'), node.get('maxWidth'), node.get('width')) if isinstance(x, (int, float))] or [1])
                if size > best[0]:
                    best[:] = [size, u]
            node = list(node.values())
        if isinstance(node, list):
            for x in node:
                walk(x)
    walk(data)
    pic = re.search(SPOT_PIC, text)
    return best[1] or (pic.group(0) if pic else '')


def tag_file(path, meta):
    """Вписывает в скачанный файл исполнителя, название и обложку. Не вышло — файл остаётся как был."""
    src = Path(path)
    ext = src.suffix.lower().lstrip('.')
    tmp, cover = src.with_name(src.stem + '.tagtmp.' + ext), HOME / f'cover{threading.get_ident()}.jpg'
    try:
        art = ext in ('mp3', 'm4a', 'flac') and bool(meta.get('thumb'))     # в Opus и WAV картинку ffmpeg не кладёт
        if art:
            try:
                fetch(meta['thumb'], cover, '', BROWSER)
            except Exception:
                art = False
        cmd = [FFMPEG or tool_path('ffmpeg.exe'), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(src)]
        if art:
            cmd += ['-i', str(cover), '-map', '0:a', '-map', '1:v', '-c', 'copy', '-disposition:v:0', 'attached_pic',
                    '-metadata:s:v', 'title=Album cover', '-metadata:s:v', 'comment=Cover (front)']
        else:
            cmd += ['-map', '0:a', '-c', 'copy']
        cmd += ['-metadata', 'title=' + meta['title'], '-metadata', 'artist=' + meta['artist']]
        cmd += (['-id3v2_version', '3'] if ext == 'mp3' else []) + [str(tmp)]
        r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, creationflags=NOWIN, timeout=180)
        if r.returncode == 0 and tmp.is_file() and tmp.stat().st_size > src.stat().st_size * .5:
            os.replace(tmp, src)
            return True
    except Exception:
        pass
    finally:
        for f in (tmp, cover, cover.with_name(cover.name + '.part')):
            try:
                f.unlink()
            except OSError:
                pass
    return False


def spotify_meta(url):
    """{'artist', 'title', 'thumb', 'dur'} трека по ссылке Spotify."""
    with LOCK:
        if url in SPOT:
            return SPOT[url]
    m = re.search(r'spotify\.com/(?:intl-[\w-]+/)?track/(\w+)', url)
    if not m:
        raise Plain(SPOT_ONLY)
    got = {'artist': '', 'title': '', 'thumb': '', 'dur': None}
    tid, seen = m.group(1), []

    def embed(text, how):
        ent = spotify_entity(json.loads(text)) if text else None
        if not ent:
            seen.append(f'embed/{how}: данных трека нет ({len(text or "")} симв.)')
            return False
        got.update(title=ent['name'].strip(), artist=', '.join(a['name'] for a in ent['artists'][:3]).strip(),
                   thumb=spotify_cover(json.loads(text), text),
                   dur=ent['duration'] / 1000 if isinstance(ent.get('duration'), (int, float)) else None)
        return bool(got['title'] and got['artist'])

    if GUI['on']:                           # надёжнее всего: открыть страницу трека в невидимом окне-браузере
        try:
            embed(browser_text(f'https://open.spotify.com/embed/track/{tid}',
                               "(function(){var e=document.getElementById('__NEXT_DATA__');return e?e.textContent:''})()"), 'окно')
        except Exception as e:
            seen.append(f'embed/окно: {e}'[:160])
    for way in (('curl', '') if WIN else ('',)):
        if got['title'] and got['artist']:
            break
        try:                                # то же простым запросом
            page = web_text(f'https://open.spotify.com/embed/track/{tid}', way)
            data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
            if embed(data.group(1) if data else '', way or 'python'):
                break
        except Exception as e:
            seen.append(f'embed/{way or "python"}: {e}'[:160])
        try:                                # обычная страница трека: название и исполнитель в её заголовке
            page = web_text(f'https://open.spotify.com/track/{tid}', way)
            head = re.search(r'<title>(.*?) - song and lyrics by (.*?) \| Spotify</title>', page, re.S)
            if head:                        # только настоящая страница трека, а не заглушка «Spotify — Web Player»
                pic = re.search(r'<meta property="og:image" content="([^"]*)"', page)
                got.update(title=html.unescape(head.group(1)).strip(), artist=html.unescape(head.group(2)).strip(),
                           thumb=html.unescape(pic.group(1)) if pic else '')
                break
            seen.append(f'track/{way or "python"}: ' + ' '.join(re.findall(r'<title>(.*?)</title>', page, re.S))[:80])
        except Exception as e:
            seen.append(f'track/{way or "python"}: {e}'[:160])
    for way in (('curl', '') if WIN else ('',)):
        if got['title'] and got['artist']:
            break
        try:                                # Spotify в России не работает и отдаёт пустую страницу; о треке знает и song.link
            page = web_text(f'https://song.link/s/{tid}', way)
            data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
            ent = (json.loads(data.group(1)).get('props', {}).get('pageProps', {}).get('pageData') or {}).get('entityData') if data else None
            if isinstance(ent, dict) and isinstance(ent.get('title'), str) and isinstance(ent.get('artistName'), str):
                got.update(title=ent['title'].strip(), artist=ent['artistName'].strip(),
                           thumb=ent['thumbnailUrl'] if str(ent.get('thumbnailUrl') or '').startswith('https://') else '',
                           dur=ent['duration'] / 1000 if isinstance(ent.get('duration'), (int, float)) else None)
            else:
                seen.append(f'song.link/{way or "python"}: данных трека нет ({len(page)} симв.)')
        except Exception as e:
            seen.append(f'song.link/{way or "python"}: {e}'[:160])
    if not (got['title'] and got['artist']):   # без исполнителя по одному названию находится чужая песня: лучше честно отказать
        try:
            (HOME / 'spotify.log').write_text('\n'.join([url, *seen]), 'utf-8')
        except OSError:
            pass
        raise Plain(SPOT_FAIL)
    with LOCK:
        SPOT[url] = got
    return got


def spotify_name(meta):
    return ' — '.join(x for x in (meta['artist'], meta['title']) if x)


SPOT_OFF = ('live', 'cover', 'remix', 'karaoke', 'slowed', 'sped up', 'nightcore', 'instrumental', 'reaction', '8d', 'концерт', 'кавер')


def spotify_pick(meta):
    """Ищет трек на YouTube и выбирает из первых результатов подходящий: та же длина, тот же исполнитель,
    не концерт и не кавер. Первый попавшийся результат часто оказывается не той записью."""
    query = ' - '.join(x for x in (meta['artist'], meta['title']) if x)
    env = dict(os.environ, PATH=str(BIN) + os.pathsep + os.environ.get('PATH', ''), PYTHONIOENCODING='utf-8')
    try:
        r = subprocess.run(ytdlp_cmd() + ['--ignore-config', '--no-colors', '--encoding', 'utf-8', '--flat-playlist', '--socket-timeout', '20',
                                          '--retries', '3', '--print', 'JT_HIT:%(id)s|%(duration)s|%(channel)s|%(title)s'] + net_args(load())
                           + ['--', 'ytsearch8:' + query], capture_output=True, stdin=subprocess.DEVNULL, env=env, creationflags=NOWIN,
                           timeout=90, encoding='utf-8', errors='replace')
        lines = r.stdout.splitlines()
    except Exception:
        lines = []
    best, low_q, first = (None, -99), query.lower(), meta['artist'].split(',')[0].strip().lower()
    for i, line in enumerate(x for x in lines if x.startswith('JT_HIT:')):
        m = re.match(r'JT_HIT:([\w-]{6,})\|([^|]*)\|([^|]*)\|(.*)', line)
        if not m:
            continue
        vid, dur, chan, title = m.group(1), num(m.group(2)), m.group(3).strip(), m.group(4).strip()
        text = (title + ' ' + chan).lower()
        score = -i
        if meta.get('dur') and dur:
            diff = abs(dur - meta['dur'])
            score += 8 if diff <= 2 else 4 if diff <= 6 else 0 if diff <= 20 else -8
        score += 4 if chan.endswith(' - Topic') else 0             # так YouTube называет каналы с официальными записями
        score += 3 if first and first in text else -3
        score += 3 if meta['title'].lower() in title.lower() else -3
        score -= sum(5 for bad in SPOT_OFF if re.search(r'(?<!\w)' + re.escape(bad) + r'(?!\w)', text) and bad not in low_q)
        if score > best[1]:
            best = (vid, score)
    return 'https://www.youtube.com/watch?v=' + best[0] if best[0] else 'ytsearch1:' + query


def source(url):
    """Что отдать yt-dlp: саму ссылку или, для Spotify, найденную на YouTube запись этого трека."""
    if not is_spotify(url):
        return url
    meta = spotify_meta(url)
    with LOCK:
        if url in PICK:
            return PICK[url]
    pick = spotify_pick(meta)
    with LOCK:
        PICK[url] = pick
    return pick


# ---------- обновление самой программы ----------
def ver(s):
    return tuple(int(x) for x in re.findall(r'\d+', s or '')[:3])


def code_version(text):
    m = re.search(r"^VERSION = '([\d.]+)'", text, re.M)
    return m.group(1) if m else ''


def code_name(text):
    m = re.search(r"^SHOWN = '([\w.]+)'", text, re.M)
    return m.group(1) if m else code_version(text)


def update_bases():
    """Откуда качать обновление. Сначала по номеру последнего коммита: так оба файла точно из одной версии и нет
    задержки, с которой GitHub обновляет ссылку на ветку. Не вышло узнать номер — прямо из ветки и с зеркала."""
    bases = []
    try:
        tmp = HOME / 'commit.tmp'
        HOME.mkdir(parents=True, exist_ok=True)
        try:
            fetch(f'https://api.github.com/repos/{REPO}/commits/main', tmp, 'обновление')
            sha = re.search(r'"sha"\s*:\s*"([0-9a-f]{40})"', tmp.read_text('utf-8', 'replace'))
        finally:
            tmp.unlink(missing_ok=True)
        if sha:
            bases.append((f'https://raw.githubusercontent.com/{REPO}/{sha.group(1)}/', ''))
    except Exception:
        pass
    return bases + [(SOURCES[0], f'?t={int(time.time())}'), (SOURCES[1], '')]


def grab(name, dest, bases):
    """Файл программы из репозитория; источники пробуются по очереди, сработавший становится первым."""
    last = None
    for base in list(bases):
        try:
            fetch(base[0] + name + base[1], dest, 'обновление')
            bases.remove(base)
            bases.insert(0, base)
            return
        except Exception as e:
            last = e
    raise last


def update_run(apply):
    """Проверка (apply=False) смотрит номер версии на GitHub. Обновление качает новый код в папку UPD и перезапускает
    программу: exe остаётся прежним, при запуске он берёт код из этой папки (run_update). Установка заново не нужна."""
    tmp = HOME / 'update.new'
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        bases = update_bases()
        grab('app/eggtube.py', tmp / 'eggtube.py', bases)
        code = (tmp / 'eggtube.py').read_text(encoding='utf-8')
        new = code_version(code)
        if not new:
            raise OSError('на GitHub лежит что-то не то')
        if ver(new) <= ver(VERSION):
            with LOCK:
                UPDATE.update(state='fresh', ver='', error='')
            return
        if not apply:
            with LOCK:
                UPDATE.update(state='found', ver=code_name(code), error='')
            return
        with LOCK:
            UPDATE.update(state='load', ver=code_name(code), error='')
        grab('app/ui.html', tmp / 'ui.html', bases)
        compile(code, 'eggtube.py', 'exec')                       # битый файл не должен стать программой
        if '</html>' not in (tmp / 'ui.html').read_text(encoding='utf-8')[-200:]:
            raise OSError('интерфейс скачан не целиком')
        UPD.mkdir(parents=True, exist_ok=True)
        if not (UPD / 'icon.ico').is_file():
            ico = ASSETS / 'icon.ico'
            try:
                shutil.copyfile(ico if ico.is_file() else ASSETS.parent / 'assets' / 'icon.ico', UPD / 'icon.ico')
            except OSError:
                pass                          # без значка в трее жить можно, без обновления — нет
        # Заменяем по одному файлу, а не папку целиком: папка занята самой работающей программой, и Windows её не отдаёт.
        # Код кладём последним: по его номеру версии программа при запуске понимает, что обновление готово.
        (UPD / 'starting').unlink(missing_ok=True)
        os.replace(tmp / 'ui.html', UPD / 'ui.html')
        os.replace(tmp / 'eggtube.py', UPD / 'eggtube.py')
        if WIN and FROZEN and RESTART['quit']:
            RESTART['on'] = True
            RESTART['quit']()
        else:
            with LOCK:
                UPDATE.update(state='error', ver=code_name(code), error='Скачано. Запусти программу заново')
    except Exception as e:
        with LOCK:
            UPDATE.update(state='error', error=str(e)[:200])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def update_watch():
    """Тихо узнаёт о новой версии: вскоре после запуска и дальше раз в двадцать минут, пока программа открыта."""
    pause = threading.Event()
    pause.wait(6)
    while True:
        with LOCK:
            idle = UPDATE['state'] in ('idle', 'fresh', 'error')
        if idle:
            Api().update_check()
        pause.wait(1200)


def run_update():
    """При запуске: если в папке обновления код новее встроенного в exe — работает он. Метка starting страхует от
    обновления, которое не смогло открыть окно: в следующий раз оно будет выброшено, и запустится встроенный код."""
    src, mark = UPD / 'eggtube.py', UPD / 'starting'
    try:
        code = src.read_text(encoding='utf-8')
        if mark.exists() or ver(code_version(code)) <= ver(VERSION):
            raise ValueError
        obj = compile(code, str(src), 'exec')
        mark.write_text('1')
    except Exception:
        shutil.rmtree(UPD, ignore_errors=True)
        return False
    try:
        exec(obj, {'__name__': '__main__', '__file__': str(src), 'UPDATED': True})
    except Exception:
        if not mark.exists():
            raise                           # окно уже открывалось: это обычная ошибка, а не негодное обновление
        shutil.rmtree(UPD, ignore_errors=True)
        return False
    return True


def ytdlp_version():
    try:
        r = subprocess.run(ytdlp_cmd() + ['--version'], capture_output=True, stdin=subprocess.DEVNULL, text=True, timeout=60,
                           creationflags=NOWIN)
        return r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def prepare(force=False):
    """Докачивает недостающее. yt-dlp обязателен, ffmpeg и deno желательны: без них работа хуже, но не встаёт."""
    with LOCK:
        if TOOL['busy']:
            return
        TOOL.update(busy=True, error='')
    errors, ver = [], ''
    try:
        for t in TOOLS:
            old = t['id'] == 'yt-dlp' and own('yt-dlp.exe') and \
                time.time() - tool('yt-dlp.exe').stat().st_mtime > FRESH_DAYS * 86400
            if YTDLP or (have(t) and not force and not old):
                continue
            try:
                install_tool(t)
            except Exception as e:
                if not have(t):
                    errors.append(f'{t["id"]}: {e}'[:300])
        ver = ytdlp_version()
    finally:
        with LOCK:
            TOOL.update(busy=False, step='', done=0, total=0, ver=ver,
                        error='; '.join(errors))
        WAKE.set()


def ytdlp_cmd():
    if YTDLP:
        return [sys.executable, YTDLP]
    return [tool_path('yt-dlp.exe') or str(tool('yt-dlp.exe'))]


# ---------- загрузка ----------
# Способы соединения с YouTube. Обычный у части провайдеров рвётся (SSL: record layer failure): фильтр провайдера
# узнаёт программу по «почерку» соединения. Тогда yt-dlp представляется браузером Chrome, а если и так не вышло —
# файл качает curl из Windows, у которого соединение устроено иначе. Сработавший способ запоминается.
NET_MODES = {'': [], 'chrome': ['--impersonate', 'chrome'], 'curl': ['--downloader', 'curl']}


def net_args(st):
    a = ['--ffmpeg-location', os.path.dirname(tool_path('ffmpeg.exe'))] if have(TOOLS[1]) else []
    if st.get('proxy'):
        a += ['--proxy', st['proxy']]
    return a + NET_MODES.get(st.get('net_mode') or '', [])


def build_args(job, st, simple=False):
    ff = have(TOOLS[1])
    eq = job.get('af') if ff else ''
    a = ytdlp_cmd() + [
        '--ignore-config', '--no-playlist', '--newline', '--no-colors', '--encoding', 'utf-8',
        '--windows-filenames', '--no-mtime', '--progress', '--no-simulate',
        '--no-quiet', '--verbose',           # --print включает тихий режим, а в нём не видно ни повторов, ни причин задержки
        '--socket-timeout', '15', '--retries', '4', '--fragment-retries', '4', '--retry-sleep', '1',
        '--concurrent-fragments', '4',       # если дорожка всё же кусочная, качать по четыре куска разом
        '--paths', str(out_dir(st)), '--output', (job.get('_name') or '%(title).120B') + ' [%(id)s]' + (' EQ' if eq else '') + '.%(ext)s',
        '--print', 'before_dl:JT_ID:%(id)s',
        '--print', 'before_dl:JT_TITLE:%(title)j',
        '--print', 'after_move:JT_FILE:%(filepath)j',
        '--print', 'after_move:JT_INFO:%(vcodec)s|%(acodec)s|%(duration)s',
        '--progress-template',
        'download:JT_P|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|'
        '%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s',
    ]
    a += net_args(st)
    if job['kind'] == 'audio':
        a += ['--format', 'ba/b']
        if ff and not eq:                    # с эквалайзером звук перекодирует finish, сразу в нужный формат
            a += ['--extract-audio', '--audio-format', job.get('aformat') or 'mp3', '--audio-quality', '0']
    elif not ff:
        a += ['--format', 'b']               # без ffmpeg дорожки не склеить: берём готовый файл
    elif simple:
        a += ['--format', 'bv*+ba/b']   # выбранный формат не сложился (нет такого кодека у видео): берём как есть
    else:
        q = job['quality']
        prefer, box, recode = VCODECS[job.get('vcodec') or 'h264']
        # proto в конце: при равном разрешении и кодеке брать дорожку по прямой ссылке, а не нарезанную на куски (HLS).
        # Иначе yt-dlp выбирает по битрейту и может взять кусочную: она стартует с задержкой и идёт в разы медленнее
        sort = ['res' if q == 'max' else 'res:' + q, 'fps'] + ([prefer] if prefer else []) + ['proto']
        a += ['--format', 'bv*+ba/b', '--format-sort', ','.join(sort)]
        # под перекодирование качаем в MKV (туда ложится что угодно), в нужный формат файл переложит finish
        a += ['--merge-output-format', 'mkv'] if recode else ['--merge-output-format', box, '--remux-video', box]
    return a + ['--', job.get('_query') or job['url']]


def post_plan(job):
    """Что наш ffmpeg должен сделать с файлом после загрузки; None — ничего."""
    if not have(TOOLS[1]) and not FFMPEG:
        return None
    af = job.get('af') or ''
    if job['kind'] == 'audio':
        return {'ext': job.get('aformat') or 'mp3', 'v': ['-vn'], 'a': ACODECS[job.get('aformat') or 'mp3'], 'af': af,
                'stage': 'Накладываю эквалайзер'} if af else None
    key = job.get('vcodec') or 'h264'
    recode = VCODECS[key][2]
    src_ext = Path(job['file']).suffix[1:].lower()
    if not recode:
        if not af:
            return None
        return {'ext': src_ext, 'v': ['-c:v', 'copy'], 'af': af, 'stage': 'Накладываю эквалайзер',
                'a': ['-c:a', 'libopus', '-b:a', '160k'] if src_ext == 'webm' else ['-c:a', 'aac', '-b:a', '192k']}
    ready = bool(re.search(VCODEC_HAVE[key], job.get('vc') or '', re.I))     # сайт сам дал нужный кодек: картинку не трогаем
    if key == 'prores':
        audio = ['-c:a', 'pcm_s16le']
    else:
        audio = ['-c:a', 'copy'] if not af and re.search(r'^(mp4a|aac)', job.get('ac') or '', re.I) else ['-c:a', 'aac', '-b:a', '192k']
    return {'ext': VCODECS[key][1], 'v': ['-c:v', 'copy'] if ready else recode, 'a': audio, 'af': af,
            'stage': 'Перекладываю в ' + VCODECS[key][1].upper() if ready else 'Перекодирую в ' + VCODEC_NAME[key]}


def finish(job, plan):
    """Один проход ffmpeg: перекодирование картинки (если просили H.265 или ProRes), звук и эквалайзер.
    У обычного видео с эквалайзером картинка копируется как есть, пережимается только звук."""
    src = Path(job['file'])
    ext = plan['ext']
    tmp, final = src.with_name(src.stem + '.eqtmp.' + ext), src.with_suffix('.' + ext)
    maps = [] if job['kind'] == 'audio' else ['-map', '0:v:0', '-map', '0:a:0?']
    cmd = [FFMPEG or tool_path('ffmpeg.exe'), '-y', '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', 'pipe:1',
           '-i', str(src)] + maps + plan['v'] + plan['a'] + (['-af', plan['af']] if plan['af'] else []) + \
        (['-movflags', '+faststart'] if ext in ('mp4', 'mov') else []) + [str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=NOWIN, encoding='utf-8', errors='replace')
    with LOCK:
        job['proc'] = proc
        if job['status'] == 'cancel':
            kill(proc)
    out, dur = [], num(job.get('dur'))
    for line in proc.stdout:
        line = line.strip()
        m = re.match(r'out_time_(?:us|ms)=(\d+)', line)      # оба поля ffmpeg отдаёт в микросекундах
        if m and dur:
            with LOCK:
                job['pct'] = min(99.9, round(int(m.group(1)) / 1e4 / dur, 1))
        elif line and not re.match(r'^[a-z_0-9]+=', line):
            out.append(line)
    code = proc.wait()
    if code or job['status'] == 'cancel' or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return code or 1, 'ffmpeg: ' + (out[-1] if out else 'не удалось обработать файл'), out
    if final != src:
        src.unlink(missing_ok=True)
    os.replace(tmp, final)
    job['file'] = str(final)
    return 0, '', out


ATTEMPTS = len(NET_MODES)
NET_ERRORS = (r'http error (403|429|5\d\d)|bytes read|more expected|incomplete|timed out|timeout|'
              r'connection (reset|aborted)|remote end closed|10054|10060|giving up after|ssl|record layer|impersonat')
HINTS = (
    (r'not a bot|sign in to confirm|login required|use --cookies', 'YouTube просит подтвердить, что ты не бот. '
     'Попробуй позже или включи VPN либо прокси.'),
    (r'bytes read|more expected|incomplete', 'Соединение с YouTube обрывается на середине файла. Нажми «Повторить»: '
     'загрузка продолжится с того же места. Если обрывается раз за разом, попробуй качество пониже или VPN.'),
    (r'timed out|timeout|10060|10054|connection (reset|aborted|refused)|unable to connect|getaddrinfo|'
     r'name resolution|ssl|eof occurred|remote end closed|read operation',
     'YouTube не отвечает или рвёт соединение. Если он у тебя замедлен, включи VPN на весь компьютер '
     'или укажи прокси в настройках.'),
    (r'http error 403|forbidden', 'YouTube отказал в выдаче файла, у него так бывает временно. Нажми «Повторить» чуть позже; '
     'если повторяется, обнови компоненты в настройках.'),
    (r'requested format is not available|no video formats', 'У этого видео нет такого варианта. '
     'Попробуй другое качество.'),
    (r'private video|members-only|age-restricted|confirm your age|unavailable|removed|blocked', 'Видео недоступно: закрытое, удалённое '
     'или с ограничением.'),
    (r'unsupported url|is not a valid url', 'Не похоже на ссылку на видео.'),
    (r'drm', 'Видео защищено DRM, скачать нельзя.'),
    (r'ffmpeg|ffprobe', 'Не хватает ffmpeg. В настройках нажми «Обновить компоненты».'),
    (r'no space|errno 28', 'На диске кончилось место.'),
)


def explain(raw):
    low = raw.lower()
    for pat, text in HINTS:
        if re.search(pat, low):
            return text
    return 'Не получилось скачать.'


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def kill(proc):
    if proc.poll() is not None:
        return
    if WIN:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True, stdin=subprocess.DEVNULL, creationflags=NOWIN)
    else:
        proc.kill()


def sweep(folder, vid):
    """После отмены убирает недокачанные куски именно этого видео."""
    if not vid:
        return
    for p in glob.glob(os.path.join(glob.escape(str(folder)), '*[[]' + glob.escape(vid) + '[]]*')):
        if re.search(r'\.(part|ytdl)$|\.part-Frag\d+$|\.f\d+\.\w+$|\.eqtmp\.\w+$', p):
            try:
                os.remove(p)
            except OSError:
                pass


def run_once(job, st, simple):
    env = dict(os.environ, PATH=str(BIN) + os.pathsep + os.environ.get('PATH', ''), PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen(build_args(job, st, simple), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, env=env, creationflags=NOWIN,
                            encoding='utf-8', errors='replace')
    with LOCK:
        job['proc'] = proc
        if job['status'] == 'cancel':
            kill(proc)
    tail, err = [], ''
    job['_tail'] = tail                        # журнал доступен и пока загрузка идёт
    for line in proc.stdout:
        line = line.rstrip('\r\n')
        if line.startswith('JT_P|'):
            f = line.split('|')
            if len(f) >= 7:
                done, total = num(f[2]), num(f[3]) or num(f[4])
                with LOCK:
                    if f[1] == 'finished':
                        job.update(pct=100, stage='Собираю файл')
                    else:
                        if done and done > job.get('got', 0):          # данные идут: старое предупреждение уже неважно
                            job.update(got=done, note='')
                        job.update(stage='Качаю', speed=num(f[5]), eta=num(f[6]), size=total,
                                   pct=round(100 * done / total, 1) if done is not None and total else job['pct'])
            continue
        if line.startswith('JT_ID:'):
            job['vid'] = line[6:].strip()
            job['stage'] = 'Подключаюсь к серверу с видео'       # видео найдено, дальше пойдут данные
        elif line.startswith('JT_TITLE:'):
            try:
                with LOCK:
                    if job.get('src') != 'spotify':          # у трека со Spotify название уже верное, не брать его с YouTube
                        job['title'] = json.loads(line[9:])
            except ValueError:
                pass
        elif line.startswith('JT_INFO:'):
            job['vc'], job['ac'], job['dur'] = (line[8:].split('|') + ['', '', ''])[:3]
        elif line.startswith('JT_FILE:'):
            try:
                with LOCK:
                    job['file'] = json.loads(line[8:])
            except ValueError:
                pass
        else:
            tail.append(line)
            del tail[:-400]
            if line.startswith('ERROR:'):
                err = line[6:].strip()
                continue
            m = re.search(r'Retrying.*?\((\d+)/(\d+)\)', line)
            with LOCK:
                if m:                                 # связь рвётся: показать номер попытки и слова yt-dlp
                    job.update(stage=f'Связь рвётся, попытка {m.group(1)} из {m.group(2)}',
                               note=re.sub(r'^(WARNING: )?\[[\w:]+\]\s*', '', line)[:220])
                elif line.startswith('WARNING:'):
                    job['note'] = re.sub(r'^\[[\w:]+\]\s*', '', line[8:].strip())[:220]
                elif re.match(r'\[(Merger|ExtractAudio|VideoRemuxer|VideoConvertor|FixupM3u8|FixupM4a)\]', line):
                    job['stage'] = 'Собираю файл'
    code = proc.wait()
    return code, err, tail


def run_job(job):
    st = load()
    try:
        out_dir(st).mkdir(parents=True, exist_ok=True)
        if job.get('src') == 'spotify' and not job.get('_query'):
            job['stage'] = 'Ищу трек'
            meta = spotify_meta(job['url'])
            name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', ' ', spotify_name(meta).replace(' — ', ' - ')).strip()[:120]
            job.update(title=spotify_name(meta), _query=source(job['url']), _name=name.replace('%', '%%'))
        modes = sorted(NET_MODES, key=lambda m: m != st['net_mode'])      # начать с того способа, что сработал в прошлый раз
        for attempt in range(1, ATTEMPTS + 1):
            st = dict(st, net_mode=modes[attempt - 1])
            code, err, tail = run_once(job, st, False)
            if not code and job['status'] != 'cancel' and load()['net_mode'] != st['net_mode']:
                keep = load()
                keep['net_mode'] = st['net_mode']
                save(keep)
            flaky = re.search(NET_ERRORS, (err + ' ' + ' '.join(x for x in tail[-12:] if 'Got error' in x or 'Giving up' in x)).lower())
            if not code or job['status'] == 'cancel' or attempt == ATTEMPTS or not flaky:
                break
            # обрыв или отказ на середине: новый заход берёт свежие ссылки и продолжает с того же места (кусок .part цел)
            job.update(stage=f'Связь оборвалась, пробую другим способом ({attempt + 1} из {ATTEMPTS})', got=0)
            for _ in range(40):
                if job['status'] == 'cancel':
                    break
                time.sleep(.1)
            if job['status'] == 'cancel':
                break
        if code and job['status'] != 'cancel' and re.search(r'format|sort|merg|remux|conver|codec|postprocess', (err or ' '.join(tail)).lower()):
            job.update(pct=0, stage='Пробую проще')
            code, err, tail = run_once(job, st, True)
        if code == 0 and job['status'] != 'cancel' and job.get('file') and os.path.isfile(job['file']):
            plan = post_plan(job)
            if plan:
                job.update(pct=0 if plan['v'][:2] != ['-c:v', 'copy'] and plan['v'] != ['-vn'] else 100, stage=plan['stage'], post=True)
                code, err, tail = finish(job, plan)
        if code == 0 and job['status'] != 'cancel' and job.get('src') == 'spotify' and job.get('file') and os.path.isfile(job['file']) and have(TOOLS[1]):
            job.update(stage='Подписываю файл')
            tag_file(job['file'], spotify_meta(job['url']))
    except Plain as e:
        code, err, tail = 1, str(e), []
        job['_say'] = str(e)
    except OSError as e:
        code, err, tail = 1, str(e), []
    with LOCK:
        job.pop('proc', None)
        if job['status'] == 'cancel':
            sweep(out_dir(st), job.get('vid'))
            if job.get('post') and job.get('file'):   # исходник под обработку уже не нужен
                Path(job['file']).unlink(missing_ok=True)
            return
        if code == 0 and job.get('file') and os.path.isfile(job['file']):
            job.update(status='done', pct=100, stage='', note='', size=os.path.getsize(job['file']))
            st = load()
            st['history'] = ([{'title': job['title'] or job['url'], 'file': job['file'], 'kind': job['kind'],
                               'eq': bool(job.get('af')),
                               'url': job['url'], 'time': int(time.time()),
                               'size': os.path.getsize(job['file'])}] + st['history'])[:HISTORY_MAX]
            save(st)
        else:
            plain = [x for x in tail if x.strip() and not x.startswith(('[debug]', 'Traceback', '  File ', '    '))]
            raw = err or (plain[-1] if plain else f'yt-dlp завершился с кодом {code}')
            job.update(status='error', stage='', error=job.pop('_say', None) or explain(raw), raw=raw[:400])
            try:
                LOG.write_text('\n'.join([job['url'], *tail]), 'utf-8')
            except OSError:
                pass


# ---------- отрывок для прослушивания эквалайзера ----------
def preview_file():
    return PREV_DIR / 'clip.mp3'


def preview_run(url, n):
    """Качает полминуты звука в mp3. Эквалайзер на него накладывает уже окно, поэтому отрывок нужен один на ссылку."""
    st, err, title = load(), '', ''
    env = dict(os.environ, PATH=str(BIN) + os.pathsep + os.environ.get('PATH', ''), PYTHONIOENCODING='utf-8')
    try:
        url = source(url)
    except Exception as e:
        with LOCK:
            if PREV['n'] == n:
                PREV.update(status='error', proc=None, error=str(e) if isinstance(e, Plain) else SPOT_FAIL)
        return
    try:
        PREV_DIR.mkdir(parents=True, exist_ok=True)
        for cut in PREV_CUTS:
            for old in PREV_DIR.iterdir():
                old.unlink()
            args = ytdlp_cmd() + [
                '--ignore-config', '--no-playlist', '--newline', '--no-colors', '--encoding', 'utf-8', '--no-simulate',
                '--socket-timeout', '25', '--retries', '4', '--force-overwrites', '--no-mtime',
                '--paths', str(PREV_DIR), '--output', 'clip.%(ext)s', '--print', 'before_dl:JT_TITLE:%(title)j',
                '--print', 'post_process:JT_PP',
                '--format', 'ba/b', '--download-sections', cut,
                '--extract-audio', '--audio-format', 'mp3', '--audio-quality', '5'] + net_args(st) + ['--', url]
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    env=env, creationflags=NOWIN, encoding='utf-8', errors='replace')
            with LOCK:
                if PREV['n'] != n:
                    kill(proc)
                    return
                PREV.update(proc=proc, stage='find')
            for line in proc.stdout:
                line = line.strip()
                if line.startswith('JT_TITLE:'):
                    try:
                        title = json.loads(line[9:])
                    except ValueError:
                        pass
                    with LOCK:
                        if PREV['n'] == n:
                            PREV.update(stage='load', title=title)
                elif line == 'JT_PP':
                    with LOCK:
                        if PREV['n'] == n:
                            PREV['stage'] = 'convert'
                elif line.startswith('ERROR:'):
                    err = line[6:].strip()
            code = proc.wait()
            with LOCK:
                if PREV['n'] != n:
                    return
                PREV['proc'] = None
                if code == 0 and preview_file().is_file() and preview_file().stat().st_size > 20000:
                    PREV.update(status='ready', title=title, error='')
                    return
    except OSError as e:
        err = str(e)
    with LOCK:
        if PREV['n'] == n:
            PREV.update(status='error', proc=None, error=explain(err) if err else 'Не получилось скачать отрывок.')


def preview_kill():
    with LOCK:
        PREV['n'] += 1
        proc, PREV['proc'] = PREV['proc'], None
        if PREV['status'] == 'loading':
            PREV.update(status='idle', url='')
    if proc:
        kill(proc)


# ---------- карточка видео под ссылкой ----------
def info_run(url, n):
    """Спрашивает у yt-dlp название, обложку, автора и длину, ничего не скачивая."""
    env = dict(os.environ, PATH=str(BIN) + os.pathsep + os.environ.get('PATH', ''), PYTHONIOENCODING='utf-8')
    got, err = {}, ''
    if is_spotify(url):                     # у Spotify спрашиваем сами: yt-dlp его не читает
        try:
            meta, fail = spotify_meta(url), ''
        except Exception as e:
            meta, fail = None, str(e) if isinstance(e, Plain) else SPOT_FAIL
        with LOCK:
            if INFO['n'] == n:
                if meta:
                    INFO.update(status='ready', title=meta['title'], thumb=meta['thumb'], author=meta['artist'], dur=meta['dur'], error='')
                else:
                    INFO.update(status='error', error=fail)
        return
    try:
        args = ytdlp_cmd() + ['--ignore-config', '--no-playlist', '--no-colors', '--encoding', 'utf-8', '--skip-download',
                              '--socket-timeout', '20', '--retries', '2'] + net_args(load())
        for key, field in (('title', 'title'), ('thumb', 'thumbnail'), ('author', 'uploader'), ('dur', 'duration')):
            args += ['--print', f'JT_{key}:%({field})j']
        proc = subprocess.Popen(args + ['--', url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, env=env, creationflags=NOWIN, encoding='utf-8', errors='replace')
        with LOCK:
            if INFO['n'] != n:
                kill(proc)
                return
            INFO['proc'] = proc
        for line in proc.stdout:
            line = line.strip()
            m = re.match(r'JT_(title|thumb|author|dur):(.*)', line)
            if m:
                try:
                    got[m.group(1)] = json.loads(m.group(2))
                except ValueError:
                    pass                      # поля нет: yt-dlp печатает NA
            elif line.startswith('ERROR:'):
                err = line[6:].strip()
        code = proc.wait()
    except OSError as e:
        code, err = 1, str(e)
    with LOCK:
        if INFO['n'] != n:
            return
        INFO['proc'] = None
        if code == 0 and got.get('title'):
            thumb = got.get('thumb') if str(got.get('thumb') or '').startswith(('http://', 'https://')) else ''
            INFO.update(status='ready', title=str(got['title']), thumb=thumb, author=str(got.get('author') or ''),
                        dur=got.get('dur') if isinstance(got.get('dur'), (int, float)) else None, error='')
        else:
            INFO.update(status='error', error=explain(err) if err else 'Не получилось узнать, что это за видео.')


def info_kill():
    with LOCK:
        INFO['n'] += 1
        proc, INFO['proc'] = INFO['proc'], None
        INFO.update(status='idle', url='')
    if proc:
        kill(proc)


def worker():
    while True:
        WAKE.wait(1)
        WAKE.clear()
        if not tools_view()['ready']:
            continue
        with LOCK:
            job = next((j for j in reversed(JOBS) if j['status'] == 'wait'), None)   # новые сверху, качаем по порядку
            if job:
                job.update(status='run', stage='Ищу видео', note='', got=0)
        if job:
            run_job(job)
            WAKE.set()


def public(job):
    return {k: v for k, v in job.items() if k != 'proc' and not k.startswith('_')}


def clipboard():
    if not WIN:
        return ''
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    u32.GetClipboardData.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not u32.OpenClipboard(None):
        return ''
    try:
        h = u32.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return ''
        p = k32.GlobalLock(h)
        if not p:
            return ''
        try:
            return ctypes.wstring_at(p)[:2000]
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def clean_url(text):
    m = re.search(r'https?://[^\s<>"\']+', text or '')
    return m.group(0) if m else ''


# ---------- то, что видит интерфейс ----------
class Api:
    def boot(self):
        st = load()
        try:
            (UPD / 'starting').unlink()      # окно открылось: обновление годное
        except OSError:
            pass
        fresh = UPDATED and st['seen'] != VERSION           # первый запуск после обновления: сказать об этом
        if st['seen'] != VERSION:
            st['seen'] = VERSION
            save(st)
        return {'version': SHOWN, 'updated': fresh, 'bands': list(EQ_BANDS), 'eq_max': EQ_MAX,
                'pt': {'max': PT_MAX, 'gain': PT_GAIN, 'f': PT_F, 'q': PT_Q, 'soft': PT_SOFT, 'fs': FS,
                       'flat': CUT_FLAT, 'cutq': CUT_Q, 'steps': CUT_STEPS},
                'settings': {k: st[k] for k in ('kind', 'quality', 'vcodec', 'aformat', 'theme', 'lang', 'layout', 'tray', 'clip', 'proxy', 'cookies',
                                                'eq', 'eq_mode', 'eq_points')},
                'dir': str(out_dir(st)), **self.poll()}

    def poll(self):
        with LOCK:
            jobs = [public(j) for j in JOBS]
            update = dict(UPDATE)
        return {'jobs': jobs, 'tools': tools_view(), 'history': load()['history'], 'update': update}

    def put(self, key, value):
        st = load()
        if key == 'kind' and value in ('video', 'audio') or key == 'quality' and value in QUALITIES \
                or key == 'cookies' and value in BROWSERS or key == 'vcodec' and value in VCODECS \
                or key == 'aformat' and value in ACODECS or key == 'lang' and value in ('ru', 'en'):
            st[key] = value
        elif key == 'layout' and value in SIZES:
            st.update(layout=value, size=list(SIZES[value]))
            if WIN:
                import webview
                webview.windows[0].resize(*SIZES[value])
        elif key == 'theme' and value in THEMES:
            st[key] = value
            if WIN:
                titlebar(value)
        elif key in ('clip', 'tray'):
            st[key] = bool(value)
        elif key == 'eq_all':                  # «Применить»: режим, полосы и точки сохраняются разом
            if not isinstance(value, dict) or value.get('mode') not in ('bands', 'graph'):
                return {'error': 'Неверные значения эквалайзера'}
            bands, points = clean_eq(value.get('bands')), clean_points(value.get('points'))
            if bands is None or points is None:
                return {'error': 'Неверные значения эквалайзера'}
            st.update(eq=bands, eq_points=points, eq_mode=value['mode'])
            save(st)
            return {'ok': True, 'eq': bands, 'eq_points': points, 'eq_mode': value['mode']}
        elif key == 'proxy':
            value = str(value).strip()
            if value and not re.match(r'^(https?|socks4a?|socks5h?)://[^\s]+$', value):
                return {'error': 'Адрес прокси выглядит так: socks5://127.0.0.1:1080'}
            st[key] = value
        else:
            return {'error': 'Неизвестная настройка'}
        save(st)
        return {'ok': True}

    def add(self, text, kind, quality):
        url = clean_url(text)
        if not url:
            return {'error': 'Вставь ссылку на видео'}
        if kind not in ('video', 'audio') or quality not in QUALITIES:
            return {'error': 'Неизвестный формат'}
        spot = is_spotify(url)
        if spot:
            kind = 'audio'                  # со Spotify берётся только звук
            if '/track/' not in url:
                return {'error': SPOT_ONLY}
        st = load()
        with LOCK:
            if any(j['url'] == url and j['kind'] == kind and j['status'] in ('wait', 'run') for j in JOBS):
                return {'error': 'Это видео уже в очереди'}
            SEQ[0] += 1
            known = INFO['title'] if INFO['url'] == url and INFO['status'] == 'ready' and not spot else ''   # название уже видно в карточке
            JOBS.insert(0, {'id': SEQ[0], 'url': url, 'kind': kind, 'src': 'spotify' if spot else '', 'quality': quality, 'title': known,
                            'af': eq_chain(st), 'vcodec': st['vcodec'], 'aformat': st['aformat'],
                            'status': 'wait', 'stage': '', 'pct': 0, 'speed': None, 'eta': None, 'size': None,
                            'file': '', 'error': '', 'raw': ''})
        WAKE.set()
        if not tools_view()['ready']:
            threading.Thread(target=prepare, daemon=True).start()
        return {'ok': True}

    def cancel(self, job_id):
        with LOCK:
            for j in JOBS:
                if j['id'] == job_id and j['status'] in ('wait', 'run'):
                    was = j['status']
                    j.update(status='cancel', stage='')
                    if was == 'run' and j.get('proc'):
                        threading.Thread(target=kill, args=(j['proc'],), daemon=True).start()
        return {'ok': True}

    def retry(self, job_id):
        with LOCK:
            for j in JOBS:
                if j['id'] == job_id and j['status'] in ('error', 'cancel'):
                    j.update(status='wait', pct=0, error='', raw='', stage='', file='', post=False, note='')
        WAKE.set()
        return {'ok': True}

    def dismiss(self, job_id):
        with LOCK:
            JOBS[:] = [j for j in JOBS if j['id'] != job_id or j['status'] in ('wait', 'run')]
        return {'ok': True}

    def clip(self):
        try:
            return clean_url(clipboard())
        except Exception:
            return ''

    def pick_dir(self):
        import webview
        r = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        if not r:
            return {'dir': str(out_dir(load()))}
        st = load()
        st['dir'] = str(r[0])
        save(st)
        return {'dir': st['dir']}

    def open_dir(self):
        d = out_dir(load())
        d.mkdir(parents=True, exist_ok=True)
        if WIN:
            os.startfile(str(d))
        return {'ok': True}

    def open_file(self, path):
        if not os.path.isfile(path):
            return {'error': 'Файла уже нет на месте'}
        if WIN:
            os.startfile(path)
        return {'ok': True}

    def reveal(self, path):
        if not os.path.isfile(path):
            return {'error': 'Файла уже нет на месте'}
        if WIN:
            subprocess.Popen('explorer /select,"' + path.replace('"', '') + '"')
        return {'ok': True}

    def forget(self):
        st = load()
        st['history'] = []
        save(st)
        return {'ok': True}

    def tools_update(self):
        with LOCK:
            if any(j['status'] == 'run' for j in JOBS):
                return {'error': 'Дождись конца загрузки'}
        threading.Thread(target=prepare, args=(True,), daemon=True).start()
        return {'ok': True}

    def update_check(self, apply=False):
        with LOCK:
            if UPDATE['state'] in ('check', 'load'):
                return {'ok': True}
            if apply and any(j['status'] in ('run', 'wait') for j in JOBS):
                return {'error': 'Дождись конца загрузки'}
            UPDATE.update(state='load' if apply else 'check', error='')
        threading.Thread(target=update_run, args=(bool(apply),), daemon=True).start()
        return {'ok': True}

    def info_start(self, text):
        url = clean_url(text)
        if not url or not tools_view()['ready']:
            info_kill()
            return {'ok': False}
        with LOCK:
            if INFO['url'] == url and INFO['status'] in ('loading', 'ready'):
                return {'ok': True}
        info_kill()
        with LOCK:
            INFO.update(status='loading', url=url, title='', thumb='', author='', dur=None, error='')
            n = INFO['n']
        threading.Thread(target=info_run, args=(url, n), daemon=True).start()
        return {'ok': True}

    def info_state(self):
        with LOCK:
            return {k: INFO[k] for k in ('status', 'url', 'title', 'thumb', 'author', 'dur', 'error')}

    def preview_start(self, text):
        url = clean_url(text)
        if not url:
            return {'error': 'Вставь ссылку, чтобы послушать отрывок'}
        if not tools_view()['ready'] or not have(TOOLS[1]):
            return {'error': 'Компоненты ещё не докачались'}
        with LOCK:
            if PREV['url'] == url and (PREV['status'] == 'loading' or PREV['status'] == 'ready' and preview_file().is_file()):
                return {'ok': True}
        preview_kill()
        with LOCK:
            PREV.update(status='loading', stage='find', url=url, title='', error='')
            n = PREV['n']
        threading.Thread(target=preview_run, args=(url, n), daemon=True).start()
        return {'ok': True}

    def preview_state(self):
        with LOCK:
            return {k: PREV[k] for k in ('status', 'stage', 'url', 'title', 'error')}

    def preview_data(self):
        try:
            return base64.b64encode(preview_file().read_bytes()).decode('ascii')
        except OSError:
            return ''

    def preview_stop(self):
        preview_kill()
        return {'ok': True}

    def open_log(self, job_id=None):
        with LOCK:
            job = next((j for j in JOBS if j['id'] == job_id), None)
            lines = list(job.get('_tail') or []) if job else []
        if lines:                                  # свежий журнал этой строки, даже если она ещё качается
            try:
                LOG.write_text('\n'.join([job['url'], *lines]), 'utf-8')
            except OSError:
                pass
        if WIN and LOG.is_file():
            os.startfile(str(LOG))
        return {'ok': True, 'lines': len(lines)}


# ---------- окно ----------
def find_window():
    """Окно программы по заголовку и классу: у папки «Яйцатюб» в проводнике заголовок такой же."""
    u32, found = ctypes.windll.user32, []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def each(h, _):
        title, cls = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(128)
        u32.GetWindowTextW(ctypes.c_void_p(h), title, 64)
        u32.GetClassNameW(ctypes.c_void_p(h), cls, 128)
        if title.value == TITLE and cls.value.startswith('WindowsForms'):
            found.append(h)
        return True

    u32.EnumWindows(proto(each), 0)
    return found[0] if found else 0


def titlebar(theme):
    h = find_window()
    if h:
        for attr, value in THEMES[theme][1]:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(h), attr, ctypes.byref(ctypes.c_int(value)), 4)


# ---------- установка на компьютер ----------
APP_DIR = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Programs' / 'Yaytsatube'
APP_EXE = APP_DIR / 'Yaytsatube.exe'
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Yaytsatube'
WORDS = {
    'install': ('Установить Яйцатюб {v} на этот компьютер?\n\nПоявятся ярлыки на рабочем столе и в меню «Пуск».',
                'Install Yaytsatube {v} on this computer?\n\nShortcuts will be added to the desktop and the Start menu.'),
    'replace': ('\n\nУже установленная версия будет заменена, настройки и история сохранятся.',
                '\n\nThe installed version will be replaced; settings and history are kept.'),
    'failed': ('Не получилось установить:\n{e}\n\nЕсли Яйцатюб сейчас открыт (в том числе в трее), закрой его и запусти установку снова. '
               'Пока программа запустится без установки.',
               'Could not install:\n{e}\n\nIf Yaytsatube is open (the tray counts), quit it and run the setup again. '
               'For now the app will start without installing.'),
    'remove': ('Удалить Яйцатюб с этого компьютера?\n\nУдалятся программа, её компоненты и настройки. Скачанные видео останутся.',
               'Remove Yaytsatube from this computer?\n\nThe app, its components and settings will be removed. Downloaded videos stay.'),
    'removed': ('Яйцатюб удалён.', 'Yaytsatube has been removed.'),
    'open': ('Открыть', 'Open'), 'quit': ('Выход', 'Quit'),
    'hidden': ('Яйцатюб свернулся в трей и продолжает работать. Выйти можно через значок у часов.',
               'Yaytsatube is still running in the tray. Use the icon next to the clock to quit.'),
}


def word(key, **kw):
    return WORDS[key][load()['lang'] == 'en'].format(**kw)


def ask(text):
    return ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x24) == 6          # вопрос, «Да / Нет»


def tell(text, icon=0x40):
    ctypes.windll.user32.MessageBoxW(None, text, TITLE, icon)


def same_path(a, b):
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def powershell(script):
    return subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
                          capture_output=True, stdin=subprocess.DEVNULL, creationflags=NOWIN)


def shortcuts(make):
    """Ярлыки на рабочем столе и в «Пуске». Папки спрашиваем у Windows: рабочий стол бывает перенесён в OneDrive."""
    q = lambda x: str(x).replace("'", "''")
    each = "foreach($d in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('Desktop'))){$p=Join-Path $d '" + q(TITLE) + ".lnk';"
    if make:
        body = ("$s=$w.CreateShortcut($p);$s.TargetPath='" + q(APP_EXE) + "';$s.WorkingDirectory='" + q(APP_DIR) +
                "';$s.IconLocation='" + q(APP_EXE) + ",0';$s.Save()}")
        return powershell('$w=New-Object -ComObject WScript.Shell;' + each + body)
    return powershell(each + 'Remove-Item -LiteralPath $p -ErrorAction SilentlyContinue}')


def stop_others():
    """Закрыть уже запущенный Яйцатюб (он может сидеть в трее), не задев себя: у собранного exe два процесса."""
    subprocess.run(['taskkill', '/F', '/IM', APP_EXE.name, '/FI', f'PID ne {os.getpid()}', '/FI', f'PID ne {os.getppid()}'],
                   capture_output=True, stdin=subprocess.DEVNULL, creationflags=NOWIN)
    time.sleep(.8)


def register():
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_SET_VALUE) as k:
        for name, value in (('DisplayName', TITLE), ('DisplayVersion', SHOWN), ('Publisher', 'owori'),
                            ('DisplayIcon', str(APP_EXE)), ('InstallLocation', str(APP_DIR)),
                            ('UninstallString', f'"{APP_EXE}" --uninstall')):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (('NoModify', 1), ('NoRepair', 1), ('EstimatedSize', APP_EXE.stat().st_size // 1024)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)


def install():
    """Копирует программу в папку пользователя, ставит ярлыки и запись в «Установленных приложениях».
    True — установлено и запущена установленная копия; False — человек отказался; None — не вышло."""
    if not ask(word('install', v=SHOWN) + (word('replace') if APP_EXE.is_file() else '')):
        return False
    try:
        me = Path(sys.executable)
        if me.name.lower() != APP_EXE.name.lower():
            stop_others()
        APP_DIR.mkdir(parents=True, exist_ok=True)
        fresh = APP_DIR / 'Yaytsatube.new'
        shutil.copyfile(me, fresh)
        os.replace(fresh, APP_EXE)
        register()
        shortcuts(True)
    except Exception as e:
        tell(word('failed', e=e), 0x30)
        return None
    subprocess.Popen(['explorer.exe', str(APP_EXE)])     # через проводник: установленная копия стартует с чистого листа
    return True


def uninstall():
    if not ask(word('remove')):
        return
    done = word('removed')              # язык берём до того, как сотрём настройки
    stop_others()
    try:
        shortcuts(False)
    except OSError:
        pass
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    shutil.rmtree(HOME, ignore_errors=True)
    tell(done)
    # сам себя exe удалить не может: папку уберёт cmd через пару секунд после нашего выхода
    subprocess.Popen(['cmd', '/c', f'ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{APP_DIR}"'], cwd=os.environ.get('TEMP') or None,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NOWIN | 0x200)


# ---------- окно и трей ----------
def raise_window(h):
    u32 = ctypes.windll.user32
    u32.ShowWindow(ctypes.c_void_p(h), 5)       # показать, если спрятано в трей
    u32.ShowWindow(ctypes.c_void_p(h), 9)       # развернуть, если свёрнуто
    u32.SetForegroundWindow(ctypes.c_void_p(h))


def gui():
    import webview
    ctypes.WinDLL('kernel32', use_last_error=True).CreateMutexW(None, False, 'EggTubeWindow2')
    if ctypes.get_last_error() == 183:      # уже запущен (возможно, сидит в трее): показать то окно
        h = find_window()
        if h:
            raise_window(h)
        return
    st = load()
    size = st['size'] or SIZES[st['layout']]      # окно открывается таким, каким его оставили
    w = webview.create_window(TITLE, str(ASSETS / 'ui.html'), js_api=Api(), width=size[0], height=size[1],
                              min_size=(440, 520), background_color=THEMES[st['theme']][0])
    tray = {'icon': None, 'quit': False, 'size': None}

    def resized(*a):                        # окно потянули мышью: запомнить размер (сохранит tray_title, не на каждый пиксель)
        nums = [x for x in a if isinstance(x, (int, float))][-2:]
        if len(nums) == 2 and nums[0] >= 440 and nums[1] >= 400:
            tray['size'] = [int(nums[0]), int(nums[1])]

    def keep_size():
        if tray['size']:
            st2 = load()
            if st2['size'] != tray['size']:
                st2.update(size=tray['size'], layout='tall' if tray['size'][0] <= 700 else 'wide')
                save(st2)
            tray['size'] = None

    def show(*_):
        w.show()
        h = find_window()
        if h:
            raise_window(h)

    def leave(*_):                          # «Выход» в меню трея: закрыть по-настоящему
        tray['quit'] = True
        w.destroy()

    def hide():
        w.hide()
        st = load()
        if not st['tray_told']:             # один раз объяснить, куда делось окно
            st['tray_told'] = True
            save(st)
            try:
                tray['icon'].notify(word('hidden'), TITLE)
            except Exception:
                pass

    def closing(*_):                        # крестик: спрятать в трей, а не выйти. Вернуть False — значит отменить закрытие
        if tray['quit'] or not tray['icon'] or not load()['tray']:
            return None
        threading.Thread(target=hide, daemon=True).start()
        return False

    def tray_run():                         # если значок не поднимется, крестик просто закроет программу, как раньше
        try:
            import pystray
            from PIL import Image
            ico = ASSETS / 'icon.ico'            # в собранном exe лежит рядом, при запуске из исходников — в assets
            with open(ico if ico.is_file() else ASSETS.parent / 'assets' / 'icon.ico', 'rb') as f:
                picture = Image.open(io.BytesIO(f.read()))     # из памяти: открытый файл значка мешал бы обновлению
            icon = pystray.Icon('Yaytsatube', picture, TITLE, pystray.Menu(
                pystray.MenuItem(word('open'), show, default=True), pystray.MenuItem(word('quit'), leave)))
            tray['icon'] = icon
            icon.run()
        except Exception:
            tray['icon'] = None

    def tray_title():                       # подсказка у значка показывает, что сейчас качается
        while True:
            time.sleep(2)
            keep_size()
            icon = tray['icon']
            if not icon:
                continue
            with LOCK:
                run = next((j for j in JOBS if j['status'] == 'run'), None)
                text = TITLE if not run else f"{TITLE}: {round(run['pct'])}%" if run['stage'] == 'Качаю' else f"{TITLE}: {run['stage']}"
            try:
                if icon.title != text:
                    icon.title = text[:120]
            except Exception:
                pass

    def started():
        w.events.shown.wait(10)
        GUI['on'] = WIN
        titlebar(load()['theme'])

    w.events.closing += closing
    RESTART['quit'] = leave
    try:
        w.events.resized += resized
    except Exception:
        pass
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=prepare, daemon=True).start()
    threading.Thread(target=tray_run, daemon=True).start()
    threading.Thread(target=tray_title, daemon=True).start()
    threading.Thread(target=update_watch, daemon=True).start()
    webview.start(started)
    keep_size()
    tray['quit'] = True
    if tray['icon']:
        try:
            tray['icon'].stop()
        except Exception:
            pass
    with LOCK:                              # программа закрывается: не оставлять yt-dlp висеть
        for j in JOBS:
            if j.get('proc'):
                j['status'] = 'cancel'
                kill(j['proc'])
    preview_kill()
    info_kill()
    if RESTART['on']:
        subprocess.Popen(['explorer.exe', sys.executable])


def selftest():
    """Проверка собранного exe (её запускает сборка на GitHub): всё ли нужное внутри."""
    import webview, pystray
    from PIL import Image
    Image.open(ASSETS / 'icon.ico').load()
    assert '</html>' in (ASSETS / 'ui.html').read_text(encoding='utf-8')[-200:]
    Path(sys.argv[sys.argv.index('--selftest') + 1]).write_text(SHOWN)


def main():
    if '--selftest' in sys.argv:
        return selftest()
    if WIN and FROZEN:
        if '--uninstall' in sys.argv:
            return uninstall()
        if not same_path(sys.executable, APP_EXE) and install() is not None:
            return                          # установили и запустили установленную копию — или человек отказался
    if not UPDATED and run_update():
        return
    gui()


if __name__ == '__main__':
    main()
