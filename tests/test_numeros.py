# 數字聽力測試：念法表、三種難度範圍、答對答錯、60 秒結束、語速與設定
import re, sys
from playwright.sync_api import sync_playwright
from common import *

R = Runner()
src = open(HTML.replace('file://', ''), encoding='utf-8').read()

# 1) 念法函式：直接從 index.html 取出來在頁面裡算（遊戲本身包在 IIFE 裡，不改遊戲程式）
m = re.search(r"const CN_DIGIT = .*?\n\s*const CN_UNIT = .*?\n", src, re.S)
f = re.search(r"function numberToChinese\(n\)\{.*?\n  \}\n", src, re.S)
assert m and f, '找不到 numberToChinese，index.html 結構變了，這支測試要跟著改'
CASES = {0:'零', 1:'一', 9:'九', 10:'十', 11:'十一', 15:'十五', 20:'二十', 22:'二十二', 99:'九十九',
         100:'一百', 101:'一百零一', 110:'一百一十', 111:'一百一十一', 200:'兩百', 202:'兩百零二', 222:'兩百二十二',
         1000:'一千', 1001:'一千零一', 1010:'一千零一十', 1100:'一千一百', 2000:'兩千', 2002:'兩千零二',
         9999:'九千九百九十九', 10000:'一萬', 10001:'一萬零一', 12345:'一萬兩千三百四十五',
         20000:'兩萬', 20202:'兩萬零兩百零二', 99999:'九萬九千九百九十九', 30000:'三萬', 70010:'七萬零一十'}

with sync_playwright() as p:
    b, pg, errs = open_page(p)
    got = pg.evaluate("(()=>{" + m.group(0) + f.group(0) + "; const o={}; for (const k of %s) o[k]=numberToChinese(k); return o})()" % list(CASES))
    for n, want in CASES.items():
        R.check(got[str(n)] == want, f'念法 {n} → {got[str(n)]}（應為 {want}）')
    b.close()

# 2) 實際玩：三種難度的出題範圍
def play(level, settings=None, n=40):
    with sync_playwright() as p:
        b, pg, errs = open_page(p, settings=settings, extra_init="try{localStorage.setItem('numeros.level','%s')}catch(e){}" % level)
        pg.click('#startListening'); pg.wait_for_timeout(300)
        nums = []
        for _ in range(n):
            txt = pg.evaluate("window.__spoken[window.__spoken.length-1].text")
            nums.append(txt)
            pg.fill('#listenInput', '1'); pg.press('#listenInput', 'Enter')   # 答錯，停在訂正畫面
            pg.wait_for_timeout(450)
            pg.click('#confirmBtn'); pg.wait_for_timeout(60)
        b.close()
        return nums, errs

CN2N = {'零':0,'一':1,'二':2,'兩':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
def parse(s):
    # 中文念法轉回數字（只為了核對範圍）
    total = 0; cur = 0; seen = False
    unit = {'十':10,'百':100,'千':1000,'萬':10000}
    for ch in s:
        if ch in CN2N: cur = CN2N[ch]; seen = True
        else:
            u = unit[ch]
            total += (cur if (seen or ch != '十') else 1) * u if (seen or ch=='十') else 0
            if ch == '十' and not seen: total += 0
            cur = 0; seen = False
    return total + cur
for level, lo, hi in (('basic', 0, 9999), ('five', 10000, 99999)):
    nums, errs = play(level)
    vals = [parse(s) for s in nums]
    R.check(all(lo <= v <= hi for v in vals), f'難度 {level}：{len(vals)} 題都在 {lo}–{hi}（最小 {min(vals)}、最大 {max(vals)}）')
    R.check(not errs, f'難度 {level}：沒有網頁錯誤 {errs}')
nums, errs = play('all', n=60)
vals = [parse(s) for s in nums]
R.check(any(v >= 10000 for v in vals) and any(v < 10000 for v in vals), '難度 all：兩種範圍都有出現')

# 3) 答對／答錯／計時／結果頁
with sync_playwright() as p:
    b, pg, errs = open_page(p)
    pg.click('#startListening'); pg.wait_for_timeout(300)
    R.check(pg.evaluate("document.getElementById('listeningScreen').classList.contains('active')"), '按開始進入作答畫面')
    R.check(pg.inner_text('#timerBadge') in ('01:00', '00:59'), '計時從 01:00 開始：' + pg.inner_text('#timerBadge'))
    # 空白不算
    pg.press('#listenInput', 'Enter'); pg.wait_for_timeout(100)
    R.check(pg.evaluate("document.getElementById('listenFeedback').innerHTML===''"), '沒填就按確認：不判分')
    # 答對：用唸出來的字反推正確數字
    n = pg.evaluate("window.__spoken.length")
    spoken = pg.evaluate("window.__spoken[window.__spoken.length-1].text")
    pg.fill('#listenInput', str(parse(spoken))); pg.press('#listenInput', 'Enter'); pg.wait_for_timeout(200)
    R.check('correct' in (pg.get_attribute('#listenFeedback', 'class') or ''), '答對：顯示對的回饋')
    pg.press('#listenInput', 'Enter'); pg.wait_for_timeout(100)   # 0.8 秒內重複送出不重複計分
    pg.wait_for_timeout(1000)
    R.check(pg.evaluate("window.__spoken.length") == n + 1, '答對 0.8 秒後出下一題並念出來')
    # 答錯：停住並再念一次，按「下一題」才換
    spoken = pg.evaluate("window.__spoken[window.__spoken.length-1].text")
    k = pg.evaluate("window.__spoken.length")
    pg.fill('#listenInput', '7'); pg.press('#listenInput', 'Enter'); pg.wait_for_timeout(200)
    R.check('wrong' in (pg.get_attribute('#listenFeedback', 'class') or ''), '答錯：顯示錯的回饋')
    R.check(pg.evaluate("window.__spoken.length") == k + 1 and pg.evaluate("window.__spoken[window.__spoken.length-1].text") == spoken, '答錯：再念一次同一題')
    R.check(spoken in pg.inner_text('#listenFeedback'), '答錯：畫面顯示正確中文念法')
    pg.wait_for_timeout(500); pg.click('#confirmBtn'); pg.wait_for_timeout(200)
    R.check(pg.evaluate("window.__spoken.length") == k + 2, '按下一題後才出新題')
    # 快轉到時間到
    pg.wait_for_timeout(100)
    b.close()

# 4) 60 秒結束：用假時間加速
with sync_playwright() as p:
    fast = "(()=>{const si=window.setInterval; window.setInterval=(f,t)=>si(f,t>=1000?20:t);})()"
    b, pg, errs = open_page(p, extra_init=fast)
    pg.click('#startListening'); pg.wait_for_timeout(300)
    pg.wait_for_function("document.getElementById('resultScreen').classList.contains('active')", timeout=8000)
    R.check(True, '時間到：進入結果頁')
    R.check(pg.inner_text('#timerBadge') == '00:00', '時間到：計時 00:00')
    R.check(pg.is_visible('#retryBtn') and pg.is_visible('#menuBtn'), '結果頁有「再玩一次」「回選單」')
    pg.click('#retryBtn'); pg.wait_for_timeout(300)
    R.check(pg.evaluate("document.getElementById('listeningScreen').classList.contains('active')"), '再玩一次：回到作答畫面')
    b.close()

# 5) 語速：三檔都念對速度（0.45／0.65／0.85）；字形與拼音注音設定
for rate, val in (('slow', 0.45), ('normal', 0.65), ('fast', 0.85)):
    with sync_playwright() as p:
        b, pg, errs = open_page(p, settings={'v':1,'script':'trad','lang':'es','phon':'pinyin','rate':rate})
        pg.click('#startListening'); pg.wait_for_timeout(300)
        r = pg.evaluate("window.__spoken[0].rate")
        R.check(abs(r - val) < 1e-6, f'語速 {rate}：念出速度 {r}（應為 {val}）')
        R.check(not errs, f'語速 {rate}：沒有網頁錯誤 {errs}')
        b.close()
for phon in ('pinyin', 'zhuyin', 'both', 'off'):
    for script in ('trad', 'simp'):
        with sync_playwright() as p:
            b, pg, errs = open_page(p, settings={'v':1,'script':script,'lang':'zh','phon':phon,'rate':'normal'})
            pg.click('#startListening'); pg.wait_for_timeout(300)
            pg.fill('#listenInput', '1'); pg.press('#listenInput', 'Enter'); pg.wait_for_timeout(300)
            fb = pg.inner_text('#listenFeedback')
            PY = re.search('[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', fb) is not None
            ZY = re.search('[ㄅ-ㄩ]', fb) is not None
            want = {'pinyin':(True,False), 'zhuyin':(False,True), 'both':(True,True), 'off':(False,False)}[phon]
            R.check((PY, ZY) == want, f'訂正畫面 字形={script} 拼音注音={phon}：拼音{"有" if PY else "無"} 注音{"有" if ZY else "無"}')
            R.check(not errs, f'  └ 沒有網頁錯誤 {errs}')
            b.close()

print('FAILS', R.fails); sys.exit(1 if R.fails else 0)
