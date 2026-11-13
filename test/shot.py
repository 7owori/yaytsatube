import asyncio, json, pathlib, subprocess, sys
from playwright.async_api import async_playwright
MOCK = r"""
const now = Math.floor(Date.now()/1000);
const D = {version:'3.0.0', pt:{max:12,gain:18,f:[20,20000],q:[0.3,8],soft:1.5,fs:48000,flat:0.71,cutq:[0.5,3],steps:4}, bands:[31,62,125,250,500,1000,2000,4000,8000,16000], eq_max:12, dir:'C:\\Users\\me\\Downloads\\Яйцатюб', settings:{kind:'video',quality:'1080',vcodec:'h264',aformat:'mp3',theme:'dark',lang:'ru',tray:true,clip:true,proxy:'',cookies:'',eq:[0,0,0,0,0,0,0,0,0,0],eq_mode:'bands',eq_points:[]},
 tools:{busy:false,step:'',done:0,total:0,error:'',ver:'2026.11.04',ready:true,have:{'yt-dlp':true,ffmpeg:true,deno:true}},
 jobs:[
  {id:4,url:'https://youtu.be/a',kind:'video',quality:'1080',title:'',status:'wait',stage:'',pct:0},
  {id:3,url:'https://youtu.be/b',kind:'video',quality:'1080',title:'Как варить яйца всмятку: полный разбор за 12 минут',status:'run',stage:'Качаю',pct:46.2,speed:3400000,eta:42,size:268000000},
  {id:2,url:'https://youtu.be/c',kind:'video',quality:'1080',title:'Обзор сковородок 2026',status:'error',stage:'',pct:0,error:'YouTube просит вход. В настройках выбери браузер, где ты вошёл в YouTube (надёжнее всего Firefox), и повтори.',raw:"[youtube] c: Sign in to confirm you're not a bot."},
  {id:1,url:'https://youtu.be/d',kind:'audio',quality:'max',title:'Lo-fi для готовки',status:'done',stage:'',pct:100,size:9400000,file:'C:\\x.mp3'}],
 history:[{title:'Lo-fi для готовки',file:'C:\\x.mp3',kind:'audio',size:9400000,time:now},{title:'Омлет по-французски за 3 минуты',file:'C:\\y.mp4',kind:'video',size:412000000,time:now-86400},{title:'Яичница, которую вы готовили неправильно',file:'C:\\z.mp4',kind:'video',size:1830000000,time:now-5*86400}]};
if (location.hash == '#first') { D.jobs = [D.jobs[0]]; D.history = []; D.tools = {busy:true,step:'ffmpeg',done:61000000,total:148000000,error:'',ver:'',ready:true,have:{'yt-dlp':true,ffmpeg:false,deno:false}}; }
window.D = D;
const ok = async () => ({ok:true});
window.pywebview = {api:{boot:async()=>D, poll:async()=>({jobs:D.jobs,tools:D.tools,history:D.history}), put:async(k,v)=>k=='eq_all'?{ok:true,eq:v.bands,eq_points:v.points.map(p=>({...p})).sort((a,b)=>a.f-b.f),eq_mode:v.mode}:{ok:true}, add:async()=>({error:'Вставь ссылку на видео'}), clip:async()=>'', cancel:ok, retry:ok, dismiss:ok, forget:ok, open_dir:ok, tools_update:ok, open_log:ok, info_start:async(u)=>{window.IV=0; window.IU=u; return {ok:!!u}}, info_state:async()=>(++window.IV<4?{status:'loading'}:/bot/.test(window.IU)?{status:'error',error:'YouTube просит подтвердить, что ты не бот. Попробуй позже или включи VPN либо прокси.'}:{status:'ready',title:'Как варить яйца всмятку: полный разбор за 12 минут',author:'Кухня на ночь',dur:754,thumb:"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 54'%3E%3Crect width='96' height='54' fill='%23c9a86a'/%3E%3Cellipse cx='48' cy='29' rx='17' ry='21' fill='%23fff8ea'/%3E%3Ccircle cx='48' cy='33' r='8' fill='%23f2b233'/%3E%3C/svg%3E"}), preview_start:async(u)=>{window.PV=0; return {ok:true}}, preview_state:async()=>(++window.PV<7?{status:'loading',stage:['find','find','load','load','convert','convert','convert'][window.PV],title:window.PV>1?'Проверочные тоны':'',error:''}:{status:'ready',stage:'convert',title:'Проверочные тоны',error:''}), preview_data:async()=>window.TONES, preview_stop:ok, reveal:ok, open_file:ok, pick_dir:async()=>({dir:D.dir})}};
"""
import base64
if not pathlib.Path('test/tones.mp3').exists():      # три тона для проверки звука; нужен ffmpeg
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error'] + sum((['-f', 'lavfi', '-i', f'sine=frequency={f}:sample_rate=48000:duration=3'] for f in (100, 1000, 8000)), [])
                   + ['-filter_complex', 'amix=inputs=3:normalize=0', '-b:a', '192k', 'test/tones.mp3'], check=True)
TONES = base64.b64encode(open('test/tones.mp3','rb').read()).decode()
pathlib.Path('test/out').mkdir(exist_ok=True)
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', args=['--no-sandbox'])
        pg = await b.new_page(viewport={'width':1024,'height':680}); errs = []
        pg.on('pageerror', lambda e: errs.append(str(e))); pg.on('console', lambda m: m.type == 'error' and errs.append(m.text))
        await pg.add_init_script(MOCK); await pg.add_init_script('window.TONES="' + TONES + '"')
        base = pathlib.Path('app/ui.html').resolve().as_uri()
        await pg.goto(base); await pg.wait_for_timeout(330); await pg.screenshot(path='test/out/b1.png'); print('первое открытие:', await pg.evaluate("[document.body.className, getComputedStyle(document.querySelector('#s1 .actions')).opacity < 1]")); await pg.wait_for_timeout(1500); print('после:', await pg.evaluate("document.body.className")); await pg.screenshot(path='test/out/s1.png')
        print('шапка:', await pg.evaluate("[$('eggFill').style.transform, $('bigEgg').className, getComputedStyle(document.querySelector('.wave')).animationPlayState, $('tLoad').textContent, $('tHist').textContent, JSON.stringify($('status').textContent), getComputedStyle($('bigEgg').firstChild).animationName]"))
        await pg.click('[data-view=s2]'); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/s2.png')
        await pg.click('[data-view=s3]'); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/s3.png')
        LEFT = """(() => { const out = []; const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          for (let n; n = w.nextNode();) { const p = n.parentElement; if (!/[А-Яа-яЁё]/.test(n.nodeValue) || p.closest('.nm, .raw, #vtitle, #vmeta, #vDir, script, style, [hidden]') ) continue; out.push(n.nodeValue.trim().slice(0, 40)); }
          document.querySelectorAll('[title],[aria-label],[placeholder]').forEach(e => { if (e.closest('.hrow, .nm, #vDir, [hidden]')) return; for (const a of ['title','aria-label','placeholder']) if (/[А-Яа-яЁё]/.test(e.getAttribute(a) || '')) out.push(a + '=' + e.getAttribute(a).slice(0, 30)); });
          return out; })()"""
        await pg.click('#langSeg [data-v=en]'); await pg.wait_for_timeout(900); print('EN настройки, осталось по-русски:', await pg.evaluate(LEFT)); await pg.screenshot(path='test/out/en3.png')
        await pg.click('[data-view=s2]'); await pg.wait_for_timeout(500); print('EN история:', await pg.evaluate(LEFT), await pg.evaluate("[...document.querySelectorAll('.hrow .tag:last-child')].map(e => e.textContent).join(' | ')"))
        await pg.click('[data-view=s2]'); await pg.wait_for_timeout(500); await pg.fill('#url', 'https://youtu.be/abc'); await pg.wait_for_timeout(2300); await pg.click('#eqBtn'); await pg.click('#eqMode [data-v=graph]'); await pg.evaluate("pts = [{t:'hp',f:90,g:0,q:.71,s:2},{t:'bell',f:1200,g:-6,q:1.4,s:1}]; sel = 1; eqShow()"); await pg.click('#qChip'); await pg.wait_for_timeout(500)
        print('EN главная:', await pg.evaluate(LEFT)); print('EN тексты:', await pg.evaluate("[$('tLoad').textContent, $('qChip').textContent.trim(), $('eqBtnText').textContent, $('ptInfo').textContent, $('prevText').textContent, [...document.querySelectorAll('.js')].map(e => e.firstChild.nodeValue).join(' | '), $('menu').children[0].textContent, $('url').placeholder.slice(0,5), $('tHist').textContent]")); await pg.screenshot(path='test/out/en1.png')
        await pg.keyboard.press('Escape'); await pg.click('#eqBtn'); await pg.fill('#url', ''); await pg.evaluate("eqLoad()")
        await pg.click('[data-view=s3]'); await pg.click('#langSeg [data-v=ru]'); await pg.wait_for_timeout(900); print('обратно RU:', await pg.evaluate("[document.querySelector('#s3 h2').textContent, document.querySelector('#s3 .sub').textContent, $('themeSeg').firstElementChild.title, $('tHist').textContent, $('eqBtnText').textContent, $('qChip').textContent.trim(), document.querySelector('.act.accent').textContent.trim()]"))
        await pg.click('#themeSeg [data-v=light]'); await pg.wait_for_timeout(250); await pg.screenshot(path='test/out/tr1.png'); print('смена темы идёт кругом:', await pg.evaluate("document.getAnimations().filter(a => a.effect && a.effect.pseudoElement).map(a => a.effect.pseudoElement).join()")); await pg.wait_for_timeout(600); await pg.click('#themeSeg [data-v=dark]'); await pg.wait_for_timeout(900)
        await pg.click('#themeSeg [data-v=light]'); await pg.wait_for_timeout(300); print('светлая тема:', await pg.evaluate("[document.documentElement.dataset.theme, getComputedStyle(document.documentElement).backgroundColor, getComputedStyle(document.querySelector('#s3 h2')).color, S.settings.theme]")); await pg.screenshot(path='test/out/t3.png')
        await pg.click('[data-view=s3]'); await pg.wait_for_timeout(300); await pg.fill('#url', 'https://youtu.be/abc'); await pg.wait_for_timeout(2300); await pg.click('#eqBtn'); await pg.click('#eqMode [data-v=graph]'); await pg.evaluate("pts = [{t:'hp',f:90,g:0,q:.71,s:2},{t:'bell',f:900,g:-6,q:1.4,s:1},{t:'hs',f:6000,g:4,q:.71,s:1}]; sel = 1; eqShow()"); await pg.wait_for_timeout(400); await pg.screenshot(path='test/out/t1.png')
        await pg.click('#eqBtn'); await pg.fill('#url', ''); await pg.wait_for_timeout(400); await pg.screenshot(path='test/out/t2.png'); await pg.evaluate("eqLoad()")
        await pg.click('[data-view=s3]'); await pg.click('#themeSeg [data-v=dark]'); await pg.click('[data-view=s3]'); print('обратно тёмная:', await pg.evaluate("[document.documentElement.dataset.theme, getComputedStyle(document.documentElement).backgroundColor]"))
        print('настройки:', await pg.evaluate("[$('vVer').textContent, document.querySelector('.corner.tr').getAttribute('aria-pressed')]"))
        await pg.click('[data-view=s3]'); print('повторный щелчок возвращает:', await pg.evaluate("[$('s1').hidden, $('s3').hidden]")); await pg.click('[data-view=s2]'); await pg.click('#s2 .back'); print('назад из истории:', await pg.evaluate("$('s1').hidden"))
        R = {}
        await pg.evaluate("go('s1')"); await pg.wait_for_timeout(250)
        w1 = await pg.evaluate("getComputedStyle(document.querySelector('.wave')).transform"); await pg.wait_for_timeout(300); w2 = await pg.evaluate("getComputedStyle(document.querySelector('.wave')).transform"); R['волны движутся'] = [w1, w2, w1 != w2]
        await pg.evaluate("window.KEEP = D.jobs; D.jobs = D.jobs.filter(j => j.status != 'run')"); await pg.wait_for_timeout(800); R['нет загрузки: яйцо целое, волны стоят'] = await pg.evaluate("[$('eggFill').style.transform, $('bigEgg').className, getComputedStyle(document.querySelector('.wave')).animationPlayState]")
        await pg.evaluate("D.jobs = KEEP.map(j => j.status == 'run' ? {...j, id: 77, pct: 3} : j)"); await pg.wait_for_timeout(900); R['старт загрузки: прыжок'] = await pg.evaluate("[$('bigEgg').className, $('eggFill').style.transform]"); await pg.wait_for_timeout(900)
        await pg.evaluate("D.jobs = KEEP"); await pg.wait_for_timeout(800)
        R['после стартовой анимации раздел не переигрывается'] = await pg.evaluate("[document.body.className, getComputedStyle($('s1')).animationName, getComputedStyle($('s1')).opacity]")
        await pg.hover('#bigEgg'); await pg.wait_for_timeout(280); R['прыжок: в полёте'] = await pg.evaluate("[$('bigEgg').className, getComputedStyle($('bigEgg').firstChild).transform]")
        await pg.mouse.move(600, 400); await pg.wait_for_timeout(750); R['прыжок: доиграл и снялся'] = await pg.evaluate("$('bigEgg').className")
        await pg.fill('#url', 'смотри https://youtu.be/abc'); await pg.wait_for_timeout(750); R['карточка: жду'] = await pg.evaluate("[$('vcard').className, $('vtitle').textContent]")
        await pg.wait_for_timeout(1300); R['карточка: готова'] = await pg.evaluate("[$('vcard').className, $('vtitle').textContent, $('vmeta').textContent, !$('vimg').hidden, Math.round($('vcard').getBoundingClientRect().height)]")
        await pg.screenshot(path='test/out/c1.png')
        await pg.fill('#url', 'https://youtu.be/bot'); await pg.wait_for_timeout(2200); R['карточка: ошибка'] = await pg.evaluate("[$('vcard').className, $('vtitle').textContent.slice(0, 40)]")
        await pg.fill('#url', ''); await pg.wait_for_timeout(500); R['карточка: убралась'] = await pg.evaluate("[$('vcard').className, Math.round($('vcard').getBoundingClientRect().height)]")
        R['кнопки видео'] = await pg.evaluate("[...document.querySelectorAll('#optRow .chip:not([hidden])')].map(c=>c.textContent.trim()).join(' | ')")
        await pg.click('#qChip'); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/m1.png')
        R['меню качества'] = await pg.evaluate("[...$('menu').children].map(b=>b.firstChild.className.includes('red')?'['+b.children[1].textContent+']':b.children[1].textContent).join(' ')")
        await pg.click('#menu button:nth-child(5)'); R['выбрал 720p'] = await pg.evaluate("[$('qChip').textContent.trim(), S.settings.quality, $('menu').hidden]")
        await pg.click('#vcChip'); await pg.click('#qChip'); R['одно меню за раз'] = await pg.evaluate("[$('menu').dataset.key, $('vcChip').getAttribute('aria-expanded'), $('qChip').getAttribute('aria-expanded')]")
        await pg.keyboard.press('Escape'); await pg.click('#vcChip'); await pg.mouse.click(600, 600); R['закрытие'] = await pg.evaluate("$('menu').hidden")
        await pg.click('#vcChip'); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/m3.png'); R['меню кодеков'] = await pg.evaluate("[...$('menu').children].map(b=>b.children[1].textContent).join(', ')"); await pg.click('#menu button:nth-child(5)'); R['выбрал ProRes'] = await pg.evaluate("[$('vcChip').textContent.trim(), S.settings.vcodec]")
        await pg.click('#eqBtn'); await pg.wait_for_timeout(200); R['эквалайзер у видео'] = await pg.evaluate("[!$('eq').hidden, $('s1').className]"); await pg.click('#eqBtn')
        await pg.click('#kindSeg [data-v=audio]'); await pg.wait_for_timeout(250)
        R['кнопки звука'] = await pg.evaluate("[...document.querySelectorAll('#optRow .chip:not([hidden])')].map(c=>c.textContent.trim()).join(' | ')")
        await pg.click('#acChip'); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/m2.png'); await pg.click('#menu button:nth-child(4)'); R['выбрал FLAC'] = await pg.evaluate("[$('acChip').textContent.trim(), S.settings.aformat]")
        await pg.click('#eqBtn'); await pg.wait_for_timeout(200)
        R['пусто'] = await pg.evaluate("[$('eqApply').disabled, $('eqReset').disabled, $('eqBtnText').textContent]")
        await pg.evaluate("document.querySelectorAll('#bands input').forEach((r,i)=>{r.value=[-10,-7,-4,-1,0,0,0,1,2,3][i]}); eqShow()")
        await pg.click('#eqApply'); await pg.wait_for_timeout(150)
        R['полосы применены'] = await pg.evaluate("[$('eqBtnText').textContent, S.settings.eq.join(), S.settings.eq_mode]")
        await pg.click('#eqMode [data-v=graph]'); await pg.wait_for_timeout(150)
        R['перешёл на график'] = await pg.evaluate("[$('eqApply').disabled, $('eqBtnText').textContent, $('bands').hidden, $('graph').hidden]")
        box = await pg.evaluate("(()=>{const r=gc.getBoundingClientRect();return [r.left,r.top,r.width,r.height]})()")
        P = lambda f, g: pg.evaluate(f"(()=>{{const r=gc.getBoundingClientRect();return [r.left+xOf({f}), r.top+yOf({g})]}})()")
        for f, g in ((60, -3), (300, -5), (3000, 4), (12000, 2)):
            x, y = await P(f, g); await pg.mouse.dblclick(x, y)
        R['4 точки'] = await pg.evaluate("pts.map(p=>[p.t,p.f,p.g,p.q,p.s].join('/')).join(' ')")
        x, y = await P(60, -3); await pg.mouse.click(x, y); await pg.click('#ptType [data-v=hp]')
        x, y = await P(60, 0); await pg.mouse.move(x, y)
        await pg.mouse.wheel(0, -100); await pg.wait_for_timeout(150); await pg.mouse.wheel(0, -100); await pg.wait_for_timeout(150)
        R['срез: колесо = крутизна'] = await pg.evaluate("[pts[0].s, pts[0].q, curveDb(60).toFixed(1), Math.max(...[40,50,60,70,80,100,150,300].map(curveDb)).toFixed(2), $('ptInfo').textContent]")
        x2, y2 = await P(60, 6); await pg.mouse.down(); await pg.mouse.move(x, (y+y2)/2); await pg.mouse.move(x2, y2); await pg.mouse.up()
        R['срез: вверх = подъём'] = await pg.evaluate("[pts[0].s, pts[0].q, curveDb(60).toFixed(1), $('ptInfo').textContent]")
        await pg.screenshot(path='test/out/e0.png')
        x, y = await P(60, 6); x2, y2 = await P(60, 0.3); await pg.mouse.move(x, y); await pg.mouse.down(); await pg.mouse.move(x2, (y+y2)/2); await pg.mouse.move(x2, y2); await pg.mouse.up()
        R['срез: обратно в ровный'] = await pg.evaluate("[pts[0].q, $('ptInfo').textContent]")
        x, y = await P(300, -5); x2, y2 = await P(200, -9)
        await pg.mouse.move(x, y); await pg.mouse.down(); await pg.mouse.move((x+x2)/2, (y+y2)/2); await pg.mouse.move(x2, y2); await pg.mouse.up()
        await pg.mouse.wheel(0, -400); await pg.wait_for_timeout(100)
        x, y = await P(12000, 2); await pg.mouse.click(x, y); await pg.click('#ptType [data-v=hs]')
        R['после правок'] = await pg.evaluate("pts.map(p=>[p.t,p.f,p.g,p.q,p.s].join('/')).join(' ')")
        R['кривая в точках'] = await pg.evaluate("[30,200,1000,3000,15000].map(f=>curveDb(f).toFixed(1)).join(' ')")
        await pg.fill('#url', 'https://youtu.be/x'); await pg.click('#go'); R['не даёт качать'] = await pg.inner_text('#addResult')
        x, y = await P(3000, 4); await pg.mouse.click(x, y); await pg.wait_for_timeout(100)
        await pg.screenshot(path='test/out/e1.png')
        await pg.click('#eqApply'); await pg.wait_for_timeout(150)
        R['график применён'] = await pg.evaluate("[$('eqApply').disabled, $('eqBtnText').textContent, S.settings.eq_mode, JSON.stringify(S.settings.eq_points)]")
        await pg.screenshot(path='test/out/e2.png')
        x, y = await P(3000, 4.1); await pg.mouse.dblclick(x, y); R['двойной щелчок по точке'] = await pg.evaluate("pts.map(p=>p.f).join()")
        x, y = await P(200, -9); await pg.mouse.click(x, y, button='right'); R['удалил правым'] = await pg.evaluate("[pts.length, $('eqApply').disabled]")
        # --- звук: то, что слышно в окне, против формулы (а формула сверена с ffmpeg)
        MEASURE = """async () => {
          const raw = atob(window.TONES), bytes = new Uint8Array(raw.length); for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
          const buf = await new OfflineAudioContext(1, 48000, 48000).decodeAudioData(bytes.buffer);
          const render = async spec => { const ctx = new OfflineAudioContext(1, buf.length, 48000), src = ctx.createBufferSource(), g = ctx.createGain();
            src.buffer = buf; g.gain.value = Math.pow(10, -spec.pre / 20); g.connect(ctx.destination); chain(ctx, src, g, spec); src.start(); return (await ctx.startRendering()).getChannelData(0); };
          const level = (d, f) => { let re = 0, im = 0; for (let i = 48000; i < d.length - 4800; i++) { re += d[i] * Math.cos(2 * Math.PI * f * i / 48000); im += d[i] * Math.sin(2 * Math.PI * f * i / 48000); } return 10 * Math.log10(re * re + im * im); };
          const spec = eqSpec(), dry = await render({ pre: 0, st: [] }), wet = await render(spec);
          return [spec.st.length, spec.pre].concat([100, 1000, 8000].map(f => (level(wet, f) - level(dry, f)).toFixed(2) + '/' + (coefsDb(spec.st.map(x => coef(x.t, x.f, x.g, x.q, 48000)), f) - spec.pre).toFixed(2)));
        }"""
        await pg.evaluate("pts = [{t:'hp',f:150,g:0,q:1.3,s:2},{t:'ls',f:300,g:5,q:.71,s:1},{t:'bell',f:1000,g:-7,q:2.5,s:1},{t:'hs',f:5000,g:6,q:1.2,s:1},{t:'lp',f:9000,g:0,q:.71,s:3}]; sel = -1; eqShow()")
        R['звук, график (слышно/формула)'] = await pg.evaluate(MEASURE)
        await pg.screenshot(path='test/out/e3.png')
        R['проигрыватель: покой'] = await pg.evaluate("[$('prevBtn').title, $('prevText').textContent, $('pload').style.width]")
        await pg.click('#prevBtn'); await pg.wait_for_timeout(1300); R['проигрыватель: качаю'] = await pg.evaluate("[$('prevBtn').title, $('prevText').textContent, $('pload').style.width]")
        await pg.screenshot(path='test/out/p1.png')
        await pg.wait_for_timeout(2200); R['проигрыватель: играет'] = await pg.evaluate("[$('prevBtn').title, $('prevText').textContent, !!asrc, anodes.length, actx.state, $('bypBtn').hidden, $('pload').style.width, $('prevTime').textContent, parseFloat($('ppos').style.width) > 0]")
        bx = await pg.evaluate("(()=>{const r=$('pline').getBoundingClientRect();return [r.left+r.width*.5, r.top+r.height/2]})()"); await pg.mouse.click(bx[0], bx[1]); await pg.wait_for_timeout(150)
        R['проигрыватель: перемотка в середину'] = await pg.evaluate("[parseFloat($('ppos').style.width).toFixed(0), $('prevTime').textContent, !!asrc, anodes.length]")
        x, y = await P(1000, -7); x2, y2 = await P(700, 3); await pg.mouse.move(x, y); await pg.mouse.down(); await pg.mouse.move((x+x2)/2, (y+y2)/2); await pg.mouse.move(x2, y2); await pg.mouse.up(); await pg.wait_for_timeout(100)
        R['на лету: двигаю точку'] = await pg.evaluate("[pts[2].f, pts[2].g, anodes[3].frequency.value.toFixed(0), anodes.length, ashape]")
        await pg.screenshot(path='test/out/e4.png')
        await pg.click('#bypBtn'); await pg.wait_for_timeout(100); R['без эквалайзера'] = await pg.evaluate("[anodes.length, bypass]"); await pg.click('#bypBtn')
        await pg.click('#prevBtn'); R['стоп'] = await pg.evaluate("[$('prevBtn').title, !!asrc, $('bypBtn').hidden, $('ppos').style.width, $('pload').style.width, $('prevTime').textContent]")
        await pg.click('#eqMode [data-v=bands]'); await pg.evaluate("document.querySelectorAll('#bands input').forEach((r,i)=>{r.value=[0,-9,-6,0,0,5,0,0,-4,8][i]}); eqShow()")
        R['звук, полосы (слышно/формула)'] = await pg.evaluate(MEASURE)
        await pg.click('#eqMode [data-v=graph]')
        R['12 точек: мс на кадр'] = await pg.evaluate("(()=>{const keep=pts; pts=[...Array(12)].map((_,i)=>({t:i%3?'bell':'hp',f:40*Math.pow(1.7,i),g:i%2?6:-6,q:1.2,s:4})); const t=performance.now(); for(let i=0;i<200;i++){pts[3].f+=1; eqShow();} const ms=(performance.now()-t)/200; pts=keep; eqShow(); return ms.toFixed(2)})()")
        await pg.click('#eqReset'); await pg.wait_for_timeout(150)
        R['сброс'] = await pg.evaluate("[$('eqReset').disabled, $('eqBtnText').textContent, pts.length, bandsDraft().join(''), S.settings.eq_points.length]")
        await pg.click('#kindSeg [data-v=video]'); R['обратно на видео'] = await pg.evaluate("[$('eq').hidden, $('qChip').hidden, $('acChip').hidden]")
        for k, v in R.items(): print(k, '→', v)
        await pg.goto(base + '#first'); await pg.reload(); await pg.wait_for_timeout(900); await pg.click('#go'); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/s4.png')
        await pg.set_viewport_size({'width':860,'height':600}); await pg.wait_for_timeout(200); await pg.screenshot(path='test/out/s5.png')
        print('errors:', errs)
        await b.close()
asyncio.run(main())
