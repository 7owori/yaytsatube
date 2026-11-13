import sys, json, os, time
a = sys.argv[1:]
if a == ['--version']: print('2026.11.04'); sys.exit(0)
url = a[-1]; get = lambda k: a[a.index(k)+1] if k in a else None
open(os.environ['FAKE_ARGS'], 'a', encoding='utf8').write(json.dumps(a, ensure_ascii=False) + '\n')
if '--skip-download' in a:
    time.sleep(.3)
    if 'bot' in url: print("ERROR: Sign in to confirm you're not a bot"); sys.exit(1)
    print('JT_title:' + json.dumps('Как варить яйца')); print('JT_thumb:"https://i.example.com/vi/abc/hq.jpg"'); print('JT_author:NA'); print('JT_dur:754')
    sys.exit(0)
if '--download-sections' in a:
    import subprocess
    open(os.environ['FAKE_ARGS'], 'a', encoding='utf8').write('')
    print('JT_TITLE:' + json.dumps('Отрывок')); sys.stdout.flush()
    time.sleep(.4)
    if 'slow' in url: time.sleep(5)
    print('JT_PP'); sys.stdout.flush(); time.sleep(.4)
    dur = '0.2' if 'short' in url and get('--download-sections') == '*30-60' else '6'
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=' + dur, os.path.join(get('--paths'), 'clip.mp3')])
    sys.exit(0)
if 'bot' in url:
    print('WARNING: something'); print("ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser"); sys.exit(1)
if 'stall' in url:
    time.sleep(.5); print('JT_ID:dQw4w9WgXcQ'); sys.stdout.flush(); time.sleep(.6)
    for i in (1, 2, 3):
        print('[debug] что-то отладочное'); print('[download] Got error: The read operation timed out. Retrying (%d/10)...' % i); sys.stdout.flush(); time.sleep(.5)
if 'flaky' in url or 'dead' in url:
    mark = os.environ['FAKE_ARGS'] + '.' + url.rsplit('/', 1)[-1]
    n = int(open(mark).read()) + 1 if os.path.exists(mark) else 1
    open(mark, 'w').write(str(n))
    if 'dead' in url or n < 3:
        print('JT_ID:dQw4w9WgXcQ'); print('JT_P|downloading|5000000|8000000|NA|100|9')
        print('[download] Got error: 1008 bytes read, 856810 more expected. Giving up after 25 retries' if n % 2 else 'ERROR: unable to download video data: HTTP Error 403: Forbidden'); sys.exit(1)
if 'sort' in url and '--format-sort' in a:
    print('ERROR: Invalid format sort field'); sys.exit(1)
print('JT_ID:dQw4w9WgXcQ'); print('JT_TITLE:' + json.dumps('Тест «видео» №1')); sys.stdout.flush()
n = 40 if 'slow' in url else 4
for part in range(1 if get('--format') == 'ba/b' else 2):
    open(os.path.join(get('--paths'), 'x [dQw4w9WgXcQ].f%d.mp4.part' % part), 'w').close()
    for i in range(1, n+1):
        print('JT_P|downloading|%d|%s|NA|%d|%d' % (i*1000000, n*1000000, 2500000, n-i)); sys.stdout.flush(); time.sleep(.05)
    print('JT_P|finished|%d|%d|NA|NA|NA' % (n*1000000, n*1000000)); sys.stdout.flush(); time.sleep(.25)
for f in os.listdir(get('--paths')):
    if f.endswith('.part'): os.remove(os.path.join(get('--paths'), f))
audio = get('--format') == 'ba/b'
real = ' EQ.' in get('--output') or get('--merge-output-format') == 'mkv'
if real:
    import subprocess
    out = os.path.join(get('--paths'), 'Тест видео №1 [dQw4w9WgXcQ]' + (' EQ.' if ' EQ.' in get('--output') else '.') + ('m4a' if audio else get('--merge-output-format') or 'mp4'))
    src = ['-f', 'lavfi', '-i', 'sine=frequency=100:sample_rate=48000:duration=3']
    if not audio: src += ['-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=10:duration=3', '-c:v', 'libx265' if 'hevcsrc' in url else 'mpeg4']
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + src + ['-c:a', 'aac', out], check=True)
else:
    out = os.path.join(get('--paths'), 'Тест видео №1 [dQw4w9WgXcQ].' + (get('--audio-format') or 'mp4'))
    open(out, 'wb').write(b'x' * 12345)
print('JT_FILE:' + json.dumps(out))
print('JT_INFO:' + ('hev1.1.6|mp4a.40.2|3' if 'hevcsrc' in url else 'mpeg4|mp4a.40.2|3' if real else 'avc1|mp4a.40.2|3'))
