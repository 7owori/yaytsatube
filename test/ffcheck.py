"""Сверка: наша формула отклика против того, что реально делает ffmpeg с синусом."""
import subprocess, re, sys, math
sys.path.insert(0, 'app'); import eggtube as E
def rms(f, af):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-f', 'lavfi', '-i', f'sine=frequency={f}:sample_rate=48000:duration=2',
                        '-af', (af + ',' if af else '') + 'atrim=start=0.5,astats=metadata=0:measure_perchannel=none', '-f', 'null', '-'], capture_output=True, text=True)
    return float(re.search(r'RMS level dB: (-?[\d.]+|-inf)', r.stderr).group(1))
cases = [{'t': 'bell', 'f': 1000, 'g': -9, 'q': 2}, {'t': 'bell', 'f': 120, 'g': 6, 'q': 0.7}, {'t': 'ls', 'f': 200, 'g': -8, 'q': 0.71},
         {'t': 'hs', 'f': 6000, 'g': 5, 'q': 1}, {'t': 'hp', 'f': 150, 'g': 0, 'q': 0.71, 's': 1}, {'t': 'lp', 'f': 8000, 'g': 0, 'q': 0.71, 's': 1},
         {'t': 'hp', 'f': 300, 'g': 0, 'q': 0.71, 's': 4}, {'t': 'lp', 'f': 2000, 'g': 0, 'q': 1.6, 's': 3}]
worst = 0
for p in cases:
    p = E.clean_points([p])[0]; af = E.graph_filter([p]); af = af.split(',', 1)[1] if af.startswith('volume') else af
    row = []
    for f in (40, 100, 200, 500, 1000, 3000, 8000, 15000):
        real = rms(f, af) - rms(f, ''); ours = E.point_db(p, f)
        if ours > -60: worst = max(worst, abs(real - ours))
        row.append(f'{real:+.1f}/{ours:+.1f}')
    print(f'{af[:44]:44s}', ' '.join(row))
import eggtube
for f0, g in ((250, -8), (4000, 6)):   # полосы: ширина в октаву
    w0 = 2 * math.pi * f0 / 48000; q = 1 / (2 * math.sinh(math.log(2) / 2 * w0 / math.sin(w0))); af = f'equalizer=f={f0}:t=o:w=1:g={g}'; row = []
    for f in (100, 200, 500, 3000, 8000):
        real = rms(f, af) - rms(f, ''); ours = E.biquad_db('bell', f0, g, q, f); worst = max(worst, abs(real - ours)); row.append(f'{real:+.1f}/{ours:+.1f}')
    print(f'{af:44s}', ' '.join(row))
allp = E.clean_points(cases[:6]); af = E.graph_filter(allp); print(af)
for f in (60, 1000, 6000):
    real = rms(f, af) - rms(f, ''); ours = sum(E.point_db(p, f) for p in allp) - float(re.match(r'volume=-([\d.]+)', af).group(1)); worst = max(worst, abs(real - ours))
print('наибольшее расхождение, дБ:', round(worst, 2))
