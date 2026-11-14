"""Яйцатюб: окно на pywebview, качает yt-dlp. Один exe, компоненты докачиваются при первом запуске."""
import base64
import ctypes
import glob
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
import urllib.request
import zipfile
from pathlib import Path

VERSION = '4.8.0'     # служебный номер для обновления: только растёт. Людям показывается SHOWN
SHOWN = '3.2'
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
# профили ProRes: (номер профиля в ffmpeg, формат пикселей, название). У 4444 цвет хранится без прореживания
PRORES = {'proxy': ('0', 'yuv422p10le', 'Proxy'), 'lt': ('1', 'yuv422p10le', 'LT'), '422': ('2', 'yuv422p10le', '422'),
          'hq': ('3', 'yuv422p10le', '422 HQ'), '4444': ('4', 'yuv444p10le', '4444')}
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
DEFAULTS = {'dir': '', 'kind': 'video', 'quality': '1080', 'vcodec': 'h264', 'aformat': 'mp3', 'theme': 'dark', 'lang': 'ru', 'layout': 'wide', 'size': None, 'tray': True, 'tray_told': False, 'seen': '', 'net_mode': '', 'prores': '422', 'clip': True, 'proxy': '', 'cookies': '',
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
    if st.get('prores') not in PRORES:
        st['prores'] = '422'
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


NO_SPOTIFY = 'Spotify не поддерживается: музыка там защищена. Вставь ссылку на этот трек с YouTube или YouTube Music.'


def is_spotify(url):
    return bool(re.match(r'https?://([\w-]+\.)*spotify\.(com|link)/', url or '', re.I))


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


def ytdlp_latest():
    """Номер последней версии yt-dlp на GitHub; пусто, если узнать не вышло."""
    tmp = HOME / 'ytdlp.tmp'
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        fetch('https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest', tmp, '')
        m = re.search(r'"tag_name"\s*:\s*"([\w.\-]+)"', tmp.read_text('utf-8', 'replace'))
        return m.group(1) if m else ''
    except Exception:
        return ''
    finally:
        tmp.unlink(missing_ok=True)


def ytdlp_old():
    """Пора ли обновить yt-dlp: вышла версия новее нашей. Не узнали, какая последняя, — судим по возрасту файла."""
    if not own('yt-dlp.exe'):
        return False
    latest = ytdlp_latest()
    if latest:
        mine = ytdlp_version()
        return bool(mine) and mine != latest
    return time.time() - tool('yt-dlp.exe').stat().st_mtime > FRESH_DAYS * 86400


def prepare(force=False, only=None):
    """Докачивает недостающее. yt-dlp обязателен, ffmpeg и deno желательны: без них работа хуже, но не встаёт."""
    with LOCK:
        if TOOL['busy']:
            return
        TOOL.update(busy=True, error='')
    errors, ver = [], ''
    try:
        for t in TOOLS:
            if only and t['id'] not in only:
                continue
            old = t['id'] == 'yt-dlp' and not force and not YTDLP and ytdlp_old()
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
# файл качает curl из Windows, у которого соединение устроено иначе. Ещё раньше пробуем старый адрес IPv4: по IPv6
# у некоторых провайдеров YouTube рвётся чаще. Сработавший способ запоминается.
NET_MODES = {'': [], 'ipv4': ['--force-ipv4'], 'chrome': ['--force-ipv4', '--impersonate', 'chrome'], 'curl': ['--force-ipv4', '--downloader', 'curl']}


def net_args(st):
    a = ['--ffmpeg-location', os.path.dirname(tool_path('ffmpeg.exe'))] if have(TOOLS[1]) else []
    if st.get('proxy'):
        a += ['--proxy', st['proxy']]
    return a + NET_MODES.get(st.get('net_mode') or '', [])


def clip_parse(clip):
    """[от, до] в секундах (любой край может быть None) -> (от, до) или текст ошибки; None — качать целиком."""
    if not clip:
        return None
    try:
        a, b = (None if x in (None, '') else float(x) for x in clip)
    except (TypeError, ValueError):
        return 'Не понял время отрывка'
    a = a or 0.0
    if not a and b is None:
        return None                         # оба края пустые: качать целиком
    if a < 0 or (b is not None and b <= a):
        return 'Конец отрывка должен быть позже начала'
    return (round(a, 2), None if b is None else round(b, 2))


def clip_name(clip):
    """Добавка к имени файла, чтобы отрывок не затёр целое видео: « 0.30-1.15»."""
    if not clip:
        return ''
    mark = lambda t: 'end' if t is None else '%d.%02d' % divmod(int(t), 60)
    return ' ' + mark(clip[0]) + '-' + mark(clip[1])


def build_args(job, st, simple=False):
    ff = have(TOOLS[1])
    eq = job.get('af') if ff else ''
    a = ytdlp_cmd() + [
        '--ignore-config', '--no-playlist', '--newline', '--no-colors', '--encoding', 'utf-8',
        '--windows-filenames', '--no-mtime', '--progress', '--no-simulate',
        '--no-quiet', '--verbose',           # --print включает тихий режим, а в нём не видно ни повторов, ни причин задержки
        '--socket-timeout', '12', '--retries', '4', '--fragment-retries', '4', '--retry-sleep', '1',
        '--extractor-retries', '1',          # YouTube молчит: не ждать по три раза, а скорее перейти к другому способу соединения
        '--concurrent-fragments', '4',       # если дорожка всё же кусочная, качать по четыре куска разом
        '--paths', str(out_dir(st)), '--output', '%(title).120B [%(id)s]' + clip_name(job.get('clip')) + (' src' if job.get('_cut') else '') + (' EQ' if eq else '') + '.%(ext)s',
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
    if job.get('clip') and not job.get('_cut'):   # отрывок: yt-dlp качает только этот кусок; у видео края режутся точно по времени
        a += ['--download-sections', '*%s-%s' % (job['clip'][0], job['clip'][1] if job['clip'][1] is not None else 'inf')]
        a += ['--force-keyframes-at-cuts'] if job['kind'] == 'video' else []
    return a + ['--', job['url']]


def has_video(path):
    """Есть ли в файле картинка. Не смогли проверить — считаем, что есть."""
    for probe in dict.fromkeys(x for x in (tool_path('ffprobe.exe'), shutil.which('ffprobe')) if x):
        try:
            r = subprocess.run([probe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(path)],
                               capture_output=True, stdin=subprocess.DEVNULL, creationflags=NOWIN, timeout=60, encoding='utf-8', errors='replace')
        except Exception:
            continue                        # этот ffprobe не запустился: пробуем следующий
        if r.returncode == 0:
            return 'video' in r.stdout
    return True


def post_plan(job):
    """Что наш ffmpeg должен сделать с файлом после загрузки; None — ничего."""
    if not have(TOOLS[1]) and not FFMPEG:
        return None
    af = job.get('af') or ''
    cut = bool(job.get('_cut'))             # файл скачан целиком: отрывок вырезаем этим же проходом
    src_ext = Path(job['file']).suffix[1:].lower()
    if job['kind'] == 'audio':
        if af:
            return {'ext': job.get('aformat') or 'mp3', 'v': ['-vn'], 'a': ACODECS[job.get('aformat') or 'mp3'], 'af': af,
                    'stage': 'Накладываю эквалайзер'}
        return {'ext': src_ext, 'v': ['-vn'], 'a': ['-c:a', 'copy'], 'af': '', 'stage': 'Вырезаю отрывок'} if cut else None
    key = job.get('vcodec') or 'h264'
    recode = VCODECS[key][2]
    if not recode:
        if not af and not cut:
            return None
        if cut:                             # при копировании картинки отрывок начался бы с ближайшего опорного кадра, а не с нужной секунды
            h264 = src_ext == 'mp4' and re.search(r'^(avc|h264)', job.get('vc') or '', re.I)
            return {'ext': src_ext, 'v': ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p'] if h264 else ['-c:v', 'copy'],
                    'af': af, 'stage': 'Вырезаю отрывок',
                    'a': (['-c:a', 'libopus', '-b:a', '160k'] if src_ext == 'webm' else ['-c:a', 'aac', '-b:a', '192k']) if af else ['-c:a', 'copy']}
        return {'ext': src_ext, 'v': ['-c:v', 'copy'], 'af': af, 'stage': 'Накладываю эквалайзер',
                'a': ['-c:a', 'libopus', '-b:a', '160k'] if src_ext == 'webm' else ['-c:a', 'aac', '-b:a', '192k']}
    ready = bool(re.search(VCODEC_HAVE[key], job.get('vc') or '', re.I))     # сайт сам дал нужный кодек: картинку не трогаем
    name = VCODEC_NAME[key]
    if key == 'prores':
        audio = ['-c:a', 'pcm_s16le']
        number, pixels, title = PRORES.get(job.get('prores'), PRORES['422'])
        recode = ['-c:v', 'prores_ks', '-profile:v', number, '-pix_fmt', pixels, '-vendor', 'apl0']
        name += ' ' + title
    else:
        audio = ['-c:a', 'copy'] if not af and re.search(r'^(mp4a|aac)', job.get('ac') or '', re.I) else ['-c:a', 'aac', '-b:a', '192k']
    return {'ext': VCODECS[key][1], 'v': ['-c:v', 'copy'] if ready else recode, 'a': audio, 'af': af,
            'stage': 'Перекладываю в ' + VCODECS[key][1].upper() if ready else 'Перекодирую в ' + name}


def finish(job, plan):
    """Один проход ffmpeg: перекодирование картинки (если просили H.265 или ProRes), звук и эквалайзер.
    У обычного видео с эквалайзером картинка копируется как есть, пережимается только звук."""
    src = Path(job['file'])
    ext = plan['ext']
    stem = ''.join(src.stem.rsplit(' src', 1)) if job.get('_cut') else src.stem      # « src» — пометка целого файла, из которого режем
    tmp, final = src.with_name(stem + '.eqtmp.' + ext), src.with_name(stem + '.' + ext)
    maps = [] if job['kind'] == 'audio' else ['-map', '0:v:0', '-map', '0:a:0?']
    clip = job.get('clip') if job.get('_cut') else None
    cut = (['-ss', str(clip[0])] + (['-to', str(clip[1])] if clip[1] is not None else [])) if clip else []
    cmd = [FFMPEG or tool_path('ffmpeg.exe'), '-y', '-hide_banner', '-loglevel', 'error', '-nostats', '-progress', 'pipe:1'] + cut + [
           '-i', str(src)] + maps + plan['v'] + plan['a'] + (['-af', plan['af']] if plan['af'] else []) + \
        (['-movflags', '+faststart'] if ext in ('mp4', 'mov') else []) + [str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=NOWIN, encoding='utf-8', errors='replace')
    with LOCK:
        job['proc'] = proc
        if job['status'] == 'cancel':
            kill(proc)
    out, dur = [], num(job.get('dur'))
    if clip and dur:
        dur = max(1, (clip[1] if clip[1] is not None else dur) - clip[0])
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
# ошибки, которые лечит свежий yt-dlp (YouTube что-то поменял) или недостающий ffmpeg
STALE = (r'http error 403|forbidden|unable to extract|nsig|signature|player response|requested format is not available|'
         r'no video formats|ffmpeg.{0,40}not (found|installed)|install ffmpeg|update yt-dlp|latest version')


def renew(text):
    """Сама обновляет то, чего не хватило загрузке: недостающий ffmpeg или устаревший yt-dlp. True — что-то изменилось."""
    if YTDLP:
        return False
    before = (ytdlp_version(), have(TOOLS[1]))
    old = own('yt-dlp.exe') and time.time() - tool('yt-dlp.exe').stat().st_mtime > 12 * 3600
    if not have(TOOLS[1]):
        prepare(False, ('ffmpeg',))
    if old and not re.search(r'ffmpeg.{0,40}not (found|installed)|install ffmpeg', text):
        prepare(True, ('yt-dlp',))
    return (ytdlp_version(), have(TOOLS[1])) != before
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
    (r'нет видеодорожки', 'YouTube отдал файл без картинки. Нажми «Повторить»; если повторится, выбери качество пониже.'),
    (r'ffmpeg exited|server returned 5|5xx|http error 5\d\d', 'YouTube не отдал файл: ошибка на его стороне. Нажми «Повторить» чуть позже.'),
    (r'ffmpeg.{0,40}not (found|installed)|ffprobe.{0,40}not (found|installed)|install ffmpeg', 'Не хватает ffmpeg, а скачать его не получилось. Проверь интернет и нажми «Повторить».'),
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
                if m:                                 # yt-dlp повторяет запрос сам: человеку это не ошибка, а «подключаюсь»
                    job.update(stage='Подключаюсь к серверу с видео', note='')
                elif re.match(r'\[(Merger|ExtractAudio|VideoRemuxer|VideoConvertor|FixupM3u8|FixupM4a)\]', line):
                    job['stage'] = 'Собираю файл'
    code = proc.wait()
    return code, err, tail


def run_job(job):
    st = load()
    try:
        out_dir(st).mkdir(parents=True, exist_ok=True)
        def attempts(st):
            modes = sorted(NET_MODES, key=lambda m: m != st['net_mode'])      # начать с того способа, что сработал в прошлый раз
            for attempt in range(1, ATTEMPTS + 1):
                st = dict(st, net_mode=modes[attempt - 1])
                code, err, tail = run_once(job, st, False)
                job['_log'] = job.get('_log', []) + [f'=== попытка {attempt}, способ: {st["net_mode"] or "обычный"} ===', *tail]
                if not code and job['status'] != 'cancel' and load()['net_mode'] != st['net_mode']:
                    keep = load()
                    keep['net_mode'] = st['net_mode']
                    save(keep)
                flaky = re.search(NET_ERRORS, (err + ' ' + ' '.join(x for x in tail[-12:] if 'Got error' in x or 'Giving up' in x)).lower())
                if not code or job['status'] == 'cancel' or attempt == ATTEMPTS or not flaky:
                    break
                # обрыв или отказ на середине: новый заход берёт свежие ссылки и продолжает с того же места (кусок .part цел)
                job.update(stage='Подключаюсь другим способом', note='', got=0)
                for _ in range(40):
                    if job['status'] == 'cancel':
                        break
                    time.sleep(.1)
                if job['status'] == 'cancel':
                    break
            return code, err, tail, st

        code, err, tail, st = attempts(st)
        text = lambda: (err + ' ' + ' '.join(tail[-40:])).lower()
        blind = lambda: (not code and job['kind'] == 'video' and job.get('file') and os.path.isfile(job['file'])
                         and not has_video(job['file']))               # видео скачалось без картинки
        if (code or blind()) and job['status'] != 'cancel' and job.get('clip') and not job.get('_cut'):
            # отрывки yt-dlp качает через ffmpeg, а ему YouTube часто отказывает (503) или отдаёт один звук.
            # Тогда качаем целиком и вырезаем сами
            if job.get('file'):
                Path(job['file']).unlink(missing_ok=True)
            sweep(out_dir(st), job.get('vid'))
            job.update(pct=0, got=0, file='', stage='Качаю целиком, чтобы вырезать отрывок', _cut=True)
            code, err, tail, st = attempts(st)
        if blind():
            code, err = 1, 'в скачанном файле нет видеодорожки'
        if code and job['status'] != 'cancel' and not job.get('_renewed') and re.search(STALE, text()) and renew(text()):
            job.update(pct=0, got=0, stage='Компоненты обновлены, пробую снова', _renewed=True)
            code, err, tail, st = attempts(st)
        if code and job['status'] != 'cancel' and re.search(r'format|sort|merg|remux|conver|codec|postprocess', (err or ' '.join(tail)).lower()):
            job.update(pct=0, stage='Пробую проще')
            code, err, tail = run_once(job, st, True)
        if code == 0 and job['status'] != 'cancel' and job.get('file') and os.path.isfile(job['file']):
            plan = post_plan(job)
            if plan:
                job.update(pct=0 if plan['v'][:2] != ['-c:v', 'copy'] and plan['v'] != ['-vn'] else 100, stage=plan['stage'], post=True)
                code, err, tail = finish(job, plan)
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
            job.update(status='error', stage='', error=explain(raw), raw=raw[:400])
            try:                            # журнал неудачи сохраняется сам: по нему видно, какие способы пробовались
                LOG.write_text('\n'.join([job['url'], *job.get('_log', []), '=== итог ===', *tail]), 'utf-8')
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
    if is_spotify(url):
        with LOCK:
            if INFO['n'] == n:
                INFO.update(status='error', error=NO_SPOTIFY)
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
                job.update(status='run', stage='Собираю данные', note='', got=0)
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
                'settings': {k: st[k] for k in ('kind', 'quality', 'vcodec', 'prores', 'aformat', 'theme', 'lang', 'layout', 'tray', 'clip', 'proxy', 'cookies',
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
                or key == 'cookies' and value in BROWSERS or key == 'vcodec' and value in VCODECS or key == 'prores' and value in PRORES \
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

    def add(self, text, kind, quality, clip=None):
        url = clean_url(text)
        if not url:
            return {'error': 'Вставь ссылку на видео'}
        if kind not in ('video', 'audio') or quality not in QUALITIES:
            return {'error': 'Неизвестный формат'}
        if is_spotify(url):
            return {'error': NO_SPOTIFY}
        clip = clip_parse(clip)
        if isinstance(clip, str):
            return {'error': clip}
        st = load()
        with LOCK:
            if any(j['url'] == url and j['kind'] == kind and j['status'] in ('wait', 'run') for j in JOBS):
                return {'error': 'Это видео уже в очереди'}
            SEQ[0] += 1
            known = INFO['title'] if INFO['url'] == url and INFO['status'] == 'ready' else ''   # название уже видно в карточке
            JOBS.insert(0, {'id': SEQ[0], 'url': url, 'kind': kind, 'clip': clip, 'quality': quality, 'title': known,
                            'af': eq_chain(st), 'vcodec': st['vcodec'], 'prores': st['prores'], 'aformat': st['aformat'],
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
            lines = (list(job.get('_log') or []) + ['=== сейчас ===', *(job.get('_tail') or [])] if job.get('_log') else list(job.get('_tail') or [])) if job else []
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
