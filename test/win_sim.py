"""Прогон кода установки и трея без Windows: системные вызовы подменены и записываются."""
import os, sys, tempfile, types, threading, time
tmp = tempfile.mkdtemp()
os.environ.update(EGGTUBE_HOME=tmp + '/home', LOCALAPPDATA=tmp + '/local', TEMP=tmp)
sys.path.insert(0, 'app'); import eggtube as E
res = []; ok = lambda c, m: (res.append(bool(c)), print(('PASS ' if c else 'FAIL ') + m))[1]
calls = []; answers = {'ask': 6}
class U32:
    def MessageBoxW(self, h, text, title, flags): calls.append(('box', text, flags)); return answers['ask'] if flags == 0x24 else 1
    def ShowWindow(self, h, n): calls.append(('showwindow', n))
    def SetForegroundWindow(self, h): calls.append(('fg',))
E.ctypes.windll = types.SimpleNamespace(user32=U32(), kernel32=types.SimpleNamespace())
reg = {}
class Key:
    def __enter__(self): return self
    def __exit__(self, *a): pass
winreg = types.SimpleNamespace(HKEY_CURRENT_USER='HKCU', KEY_SET_VALUE=2, REG_SZ=1, REG_DWORD=4,
    CreateKeyEx=lambda hive, path, r, access: (reg.setdefault(path, {}), Key())[1],
    SetValueEx=lambda k, name, r, kind, value: reg[E.UNINSTALL_KEY].__setitem__(name, (kind, value)),
    DeleteKey=lambda hive, path: reg.pop(path))
sys.modules['winreg'] = winreg
class Done: returncode = 0; stdout = b''; stderr = b''
E.subprocess.run = lambda cmd, **kw: (calls.append(('run', cmd)), Done())[1]
E.subprocess.Popen = lambda cmd, **kw: calls.append(('popen', cmd, kw.get('cwd')))
real_sleep = E.time.sleep; E.time.sleep = lambda s: None
setup = tmp + '/Downloads/Yaytsatube-Setup.exe'; os.makedirs(tmp + '/Downloads'); open(setup, 'wb').write(b'MZ' + b'x' * 5000)
E.sys.executable = setup; E.WIN = True; E.FROZEN = True; E.gui = lambda: calls.append(('gui',))

# отказ от установки
answers['ask'] = 7; E.main(); ok(not E.APP_EXE.exists() and ('gui',) not in calls and calls[0][0] == 'box' and 'Установить Яйцатюб 3' in calls[0][1], 'отказался: ничего не установлено, программа не запустилась')
# установка
calls.clear(); answers['ask'] = 6; E.main()
ps = [c[1][-1] for c in calls if c[0] == 'run' and c[1][0] == 'powershell']
ok(E.APP_EXE.read_bytes() == open(setup, 'rb').read() and not (E.APP_DIR / 'Yaytsatube.new').exists(), 'exe скопирован в ' + str(E.APP_EXE).replace(tmp, '%LOCALAPPDATA%'.replace('%LOCALAPPDATA%', '')))
r = reg.get(E.UNINSTALL_KEY, {})
ok(r.get('DisplayName') == (1, 'Яйцатюб') and r.get('DisplayVersion') == (1, E.VERSION) and r.get('UninstallString') == (1, '"%s" --uninstall' % E.APP_EXE) and r.get('EstimatedSize') == (4, 4) and r.get('Publisher') == (1, 'owori'), 'запись в «Установленных приложениях»')
ok(len(ps) == 1 and "GetFolderPath('Desktop')" in ps[0] and "GetFolderPath('Programs')" in ps[0] and "Яйцатюб.lnk" in ps[0] and "TargetPath='%s'" % E.APP_EXE in ps[0], 'ярлыки на рабочем столе и в «Пуске»')
ok(any(c[0] == 'run' and c[1][0] == 'taskkill' and 'PID ne %d' % os.getpid() in c[1] and 'PID ne %d' % os.getppid() in c[1] for c in calls), 'старая копия закрывается, свои процессы не трогаются')
ok(calls[-1] == ('popen', ['explorer.exe', str(E.APP_EXE)], None) and ('gui',) not in calls, 'после установки запускается установленная копия')
# повторная установка поверх
calls.clear(); E.main(); ok('будет заменена' in calls[0][1], 'поверх старой: предупреждает о замене')
# запуск установленной копии: без вопросов
calls.clear(); E.sys.executable = str(E.APP_EXE); E.main(); ok(calls == [('gui',)], 'установленная копия просто запускается')
# сбой установки: сообщение и запуск без установки
calls.clear(); E.sys.executable = setup; old = E.shutil.copyfile; E.shutil.copyfile = lambda a, b: (_ for _ in ()).throw(PermissionError('файл занят'))
E.main(); E.shutil.copyfile = old; ok(any(c[0] == 'box' and 'файл занят' in c[1] and c[2] == 0x30 for c in calls) and calls[-1] == ('gui',), 'не установилось: объяснил и запустился как есть')
# удаление
os.makedirs(E.HOME / 'bin', exist_ok=True); (E.HOME / 'state.json').write_text('{}'); calls.clear(); E.sys.executable = str(E.APP_EXE); E.sys.argv = ['x', '--uninstall']; E.main()
ps = [c[1][-1] for c in calls if c[0] == 'run' and c[1][0] == 'powershell']
ok(E.UNINSTALL_KEY not in reg and not E.HOME.exists() and 'Remove-Item' in ps[0] and calls[-1][0] == 'popen' and 'rmdir /s /q "%s"' % E.APP_DIR in calls[-1][1][2] and calls[-1][2] == tmp and ('gui',) not in calls, 'удаление: реестр, ярлыки, настройки, папка')
answers['ask'] = 7; calls.clear(); reg[E.UNINSTALL_KEY] = {}; E.main(); ok(E.UNINSTALL_KEY in reg and len(calls) == 1, 'удаление: отказ ничего не трогает'); E.sys.argv = ['x']

# ---- трей и закрытие окна
time.sleep = real_sleep
import importlib; importlib.reload  # noqa
os.environ['EGGTUBE_HOME'] = tmp + '/home2'
sys.modules.pop('eggtube'); import eggtube as G
G.ctypes.windll = E.ctypes.windll; G.ctypes.WinDLL = lambda *a, **k: types.SimpleNamespace(CreateMutexW=lambda *a: 1); G.ctypes.get_last_error = lambda: 0
G.find_window = lambda: 1234; G.titlebar = lambda t: None; G.worker = lambda: None; G.prepare = lambda force=False: None
log = []
class Ev:
    def __init__(self): self.fns = []; self.shown = types.SimpleNamespace(wait=lambda t: True)
    def __iadd__(self, f): self.fns.append(f); return self
class Win:
    def __init__(self): self.events = types.SimpleNamespace(closing=Ev(), shown=types.SimpleNamespace(wait=lambda t: True)); self.alive = True
    def hide(self): log.append('hide')
    def show(self): log.append('show')
    def destroy(self): log.append('destroy'); self.alive = False
    def close(self):            # как это делает pywebview: False от обработчика отменяет закрытие
        if any(f() is False for f in self.events.closing.fns): return False
        self.alive = False; return True
win = Win()
class Icon:
    last = None
    def __init__(self, name, image, title, menu): self.title = title; self.menu = menu; self.ev = threading.Event(); Icon.last = self; self.notes = []
    def run(self): self.ev.wait()
    def stop(self): log.append('icon.stop'); self.ev.set()
    def notify(self, text, title): self.notes.append(text)
pystray = types.SimpleNamespace(Icon=Icon, Menu=lambda *items: items, MenuItem=lambda text, action, default=False: types.SimpleNamespace(text=text, action=action, default=default))
sys.modules['pystray'] = pystray; sys.modules['PIL'] = types.SimpleNamespace(Image=types.SimpleNamespace(open=lambda p: 'img')); sys.modules['PIL.Image'] = sys.modules['PIL'].Image
steps = {}
def start(cb):
    cb(); time.sleep(.3); icon = Icon.last
    steps['menu'] = [(i.text, i.default) for i in icon.menu]
    steps['close1'] = win.close(); time.sleep(.3); steps['after1'] = list(log); steps['notes'] = list(icon.notes)
    steps['close2'] = win.close(); time.sleep(.2); steps['notes2'] = list(icon.notes)
    icon.menu[0].action(); steps['afteropen'] = list(log)
    st = G.load(); st['tray'] = False; G.save(st); steps['close_off'] = win.close(); win.alive = True; st['tray'] = True; G.save(st)
    icon.menu[1].action(); steps['close3'] = win.close()
sys.modules['webview'] = types.SimpleNamespace(create_window=lambda *a, **k: win, start=start)
G.gui()
ok(steps['menu'] == [('Открыть', True), ('Выход', False)], 'меню трея: «Открыть» по щелчку, «Выход»')
ok(steps['close1'] is False and steps['after1'] == ['hide'] and len(steps['notes']) == 1 and 'трей' in steps['notes'][0], 'крестик прячет окно в трей и один раз объясняет это')
ok(steps['close2'] is False and len(steps['notes2']) == 1, 'второй раз подсказка не показывается')
ok(steps['afteropen'][-1] == 'show' and ('showwindow', 5) in calls, '«Открыть» возвращает окно')
ok(steps['close_off'] is True, 'настройка выключена: крестик закрывает программу')
ok('destroy' in log and steps['close3'] is True and log[-1] == 'icon.stop', '«Выход» закрывает по-настоящему и убирает значок')
print('ИТОГО', sum(res), 'из', len(res))
