#!/usr/bin/env python3
"""Mogamii合同会社 コーポレートサイト 静的サイトビルダー

src/content/pages/ の原稿（簡易Markdown）と、このファイル内のテンプレートから public/ を生成する。
使い方: python3 src/build.py

- ビルドのたびに public/ を空にしてから生成する（古いファイルを残さない）。
  public/ に直接ファイルを置かないこと。CSSなどの静的ファイルは src/assets/ に置く。
- src/assets/ の中身は、そのまま public/assets/ にコピーする。
- 外部ライブラリ不要。生成物は外部CDN・外部フォント・JS・解析タグを含まない静的HTML。
- 見出しの書体は src/assets/fonts/ に置いた自前のフォント（サイトで使う文字だけに絞ったもの）。
  文章を変えて新しい文字が増えたら、ビルド後に python3 src/subset_fonts.py を実行して作り直す
  （fonttools と brotli が必要。無くてもサイトは表示でき、足りない文字だけ端末の書体になる）。
- src/assets/root/ の中身（favicon.ico など）は public/ の直下にコピーする。
"""
import html
import math
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "content"
ASSETS = ROOT / "src" / "assets"
OUT = ROOT / "public"
# トップページのURLは http://mogamii.com/ （2026-11-14 長坂の指定）。
# https の証明書が発行され、https に切り替えると決めたら、ここと check.py の SITE を直す。
SITE = "http://mogamii.com"
TODAY = "2026-11-13"
EMAIL = "info@mogamii.com"
EMAIL_WBR = EMAIL.replace("@", "@<wbr>")
YOUTUBE = "https://www.youtube.com/@pomodoro.shosai"
CORP = "Mogamii合同会社"

# 会社の基本情報（与えられた事実だけを載せる。番地・電話番号は載せない）
COMPANY = dict(name=CORP, rep="長坂 留樹", founded="2024年8月13日", founded_iso="2024-08-13",
               area="神奈川県横浜市", url=SITE)

AD_NOTICE = "当社のSNSなどでの情報発信には、アフィリエイト広告が含まれる場合があります。"


def E(s):
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- 簡易Markdown
def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)

    def link(m):
        text, url = m.group(1), m.group(2)
        if url.startswith("http"):
            return f'<a href="{url}" target="_blank" rel="noopener">{text}</a>'
        return f'<a href="{url}">{text}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def table(rows):
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]

    head = cells(rows[0])
    th = "".join(f'<th scope="col">{inline(c)}</th>' for c in head)
    trs = []
    for r in rows[2:]:
        tds = "".join(
            f'<th scope="row">{inline(c)}</th>' if k == 0 else f"<td>{inline(c)}</td>"
            for k, c in enumerate(cells(r)))
        trs.append(f"<tr>{tds}</tr>")
    return (f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


LISTS = [
    (re.compile(r"^- \[ \] "), "ul", ' class="checklist"'),
    (re.compile(r"^- "), "ul", ""),
    (re.compile(r"^\d+\. "), "ol", ""),
]
BLOCK_START = re.compile(r"^(- |\d+\. |\||#{2,4} |:::|```|> |<)")


def md(text):
    lines = text.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):  # コード枠
            j, buf = i + 1, []
            while j < n and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            label = s[3:].strip()
            cap = f'<p class="prompt__label">{inline(label)}</p>' if label else ""
            code = html.escape("\n".join(buf), quote=False)
            out.append(f'<div class="prompt">{cap}<pre><code>{code}</code></pre></div>')
            i = j + 1
            continue
        if s.startswith(":::"):  # 囲み（:::kind タイトル ... :::）
            kind, _, title = s[3:].partition(" ")
            j, buf, depth = i + 1, [], 0
            while j < n:
                t = lines[j].strip()
                if t == ":::":
                    if depth == 0:
                        break
                    depth -= 1
                elif t.startswith(":::"):
                    depth += 1
                buf.append(lines[j])
                j += 1
            ttl = f'<p class="callout__title">{inline(title)}</p>' if title else ""
            out.append(f'<div class="callout callout--{kind}">{ttl}{md(chr(10).join(buf))}</div>')
            i = j + 1
            continue
        if s.startswith("<"):  # 生HTML
            j, buf = i, []
            while j < n and lines[j].strip():
                buf.append(lines[j])
                j += 1
            out.append("\n".join(buf))
            i = j
            continue
        m = re.match(r"^(#{2,4}) (.*)$", s)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>")
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(table(rows))
            continue
        if s.startswith("> "):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{md(chr(10).join(buf))}</blockquote>")
            continue
        hit = False
        for rx, tag, attr in LISTS:
            if rx.match(s):
                items = []
                while i < n and rx.match(lines[i].strip()):
                    items.append(rx.sub("", lines[i].strip(), count=1))
                    i += 1
                lis = "".join(f"<li>{inline(x)}</li>" for x in items)
                out.append(f"<{tag}{attr}>{lis}</{tag}>")
                hit = True
                break
        if hit:
            continue
        buf = []
        while i < n and lines[i].strip():
            t = lines[i].strip()
            if buf and BLOCK_START.match(t):
                break
            buf.append(t)
            i += 1
        out.append(f"<p>{inline(''.join(buf))}</p>")
    return "\n".join(out)


def add_ids(body):
    """h2 に id を付ける。`## 見出し {#id}` で id を指定できる（ページ内リンク用）。"""
    count = [0]

    def rep(m):
        count[0] += 1
        title, given = m.group(1).strip(), m.group(2)
        return f'<h2 id="{given or f"sec-{count[0]}"}">{title}</h2>'

    return re.sub(r"<h2>(.*?)(?:\s*\{#([\w-]+)\})?</h2>", rep, body)


# ---------------------------------------------------------------- SVG
def burst_points(n, r1, r2, cx, cy):
    pts = []
    for k in range(n * 2):
        r = r1 if k % 2 == 0 else r2
        a = math.pi * k / n - math.pi / 2
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)


LOGO_INNER = (
    f'<polygon points="{burst_points(12, 31, 25.5, 32, 32)}" fill="#ff2e88" stroke="#141414" '
    'stroke-width="2.5" stroke-linejoin="round"/>'
    '<circle cx="32" cy="32" r="17.5" fill="#ffe14d" stroke="#141414" stroke-width="2.5"/>'
    '<path d="M22.5 41.5V23.5l9.5 10 9.5-10v18" fill="none" stroke="#141414" stroke-width="4.5" '
    'stroke-linecap="round" stroke-linejoin="round"/>')
LOGO = (f'<svg class="logo__mark" viewBox="0 0 64 64" width="44" height="44" aria-hidden="true" '
        f'focusable="false">{LOGO_INNER}</svg>')
FAVICON = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{LOGO_INNER}</svg>\n'


# 事業ごとのアイコン（装飾。viewBox 0 0 64 64）
ICONS = {
    "media": ('<path d="M9 25h11l23-12v38L20 39H9z" fill="#fff" stroke="#141414" stroke-width="3" stroke-linejoin="round"/>'
              '<path d="M20 39l4 13h8l-3-12" fill="#fff" stroke="#141414" stroke-width="3" stroke-linejoin="round"/>'
              '<path d="M49 24c4 3.5 4 13 0 16.5M54.5 19c7.5 6.5 7.5 20 0 26.5" fill="none" stroke="#141414" '
              'stroke-width="3" stroke-linecap="round"/>'),
    "ai": ('<path d="M26 6c2.4 14 8.6 20.2 22.6 22.6-14 2.4-20.2 8.6-22.6 22.6-2.4-14-8.6-20.2-22.6-22.6C17.4 26.2 23.6 20 26 6z" '
           'fill="#fff" stroke="#141414" stroke-width="3" stroke-linejoin="round"/>'
           '<path d="M50 36c1.1 6.4 3.9 9.2 10.3 10.3-6.4 1.1-9.2 3.9-10.3 10.3-1.1-6.4-3.9-9.2-10.3-10.3C46.1 45.2 48.9 42.4 50 36z" '
           'fill="#ffe14d" stroke="#141414" stroke-width="2.5" stroke-linejoin="round"/>'),
    "youtube": ('<path d="M25 47V17l27-6v30" fill="none" stroke="#141414" stroke-width="4" stroke-linejoin="round" '
                'stroke-linecap="round"/><path d="M25 25l27-6" fill="none" stroke="#141414" stroke-width="4"/>'
                '<ellipse cx="18.5" cy="47" rx="7.5" ry="6" fill="#fff" stroke="#141414" stroke-width="3"/>'
                '<ellipse cx="45.5" cy="41" rx="7.5" ry="6" fill="#fff" stroke="#141414" stroke-width="3"/>'),
}


def icon(key, cls):
    return (f'<svg class="{cls}" viewBox="0 0 64 64" width="64" height="64" aria-hidden="true" focusable="false">'
            f'{ICONS[key]}</svg>')


# ---------------------------------------------------------------- サイトデータ
NEWTAB = '<span class="sr-only">（新しいタブで開きます）</span><span aria-hidden="true"> ↗</span>'

SERVICES = [
    dict(id="media", num="01", en="WEB MEDIA & SNS", color="pink", name="Webメディア・SNS運営",
         card="SNSでの情報発信と、Webメディアの企画・運営。アフィリエイトプログラムを含む広告による収益化を行います。",
         body="""<p class="svc__lead">SNSでの情報発信を中心に、Webメディアの企画・運営を行っています。</p>
<p>この事業では、アフィリエイトプログラムを含む広告による収益化を行います。アフィリエイトプログラムとは、発信の中で紹介した商品やサービスが、リンクを経由して購入・申し込みされたときに、紹介した側が報酬を受け取る、成果報酬型の広告のしくみです。</p>
<h3 class="svc__h">主な内容</h3>
<ul class="svc__list">
  <li>SNSでの情報発信（投稿の企画・制作・運用）</li>
  <li>Webメディアの企画・運営</li>
  <li>アフィリエイトプログラムを含む広告による収益化</li>
</ul>
<div class="svc__note" role="note">
  <p class="svc__note-title"><span class="pr-badge">PR</span>広告の表示について</p>
  <p>広告を含む投稿やページには、「PR」「広告」など、広告であることが分かる表示を行います。報酬の有無や金額によって、紹介する内容の評価を変えることはありません。詳しくは<a href="disclaimer.html#ad">広告掲載について</a>をご覧ください。</p>
</div>"""),
    dict(id="ai", num="02", en="GENERATIVE AI", color="yellow", name="生成AIを活用したコンテンツ制作",
         card="生成AIを活用して、コンテンツを企画・制作します。公開する前には、人の目で内容を確認します。",
         body="""<p class="svc__lead">生成AIを活用して、コンテンツの企画・制作を行っています。</p>
<p>アイデア出しや構成づくり、下書きなど、制作のさまざまな工程で生成AIを活用しています。AIが出力したものをそのまま公開することはせず、人が内容を確認し、手を加えたうえで公開します。</p>
<h3 class="svc__h">制作で大切にしていること</h3>
<ul class="svc__list">
  <li><strong>事実の確認</strong>：数字や固有名詞などは、AIの出力をうのみにせず、確かな情報と照らし合わせて確認します。</li>
  <li><strong>権利への配慮</strong>：他者の著作物・商標・肖像などの権利を侵害しないよう注意します。</li>
  <li><strong>表現の確認</strong>：誤解を招く表現や、実際よりよく見せる表現になっていないかを確認します。</li>
</ul>"""),
    dict(id="youtube", num="03", en="YOUTUBE", color="cyan", name="YouTubeチャンネル運営",
         card="勉強用BGMチャンネル「ポモドーロ書斎」（@pomodoro.shosai）を、自社で運営しています。",
         body=f"""<p class="svc__lead">自社で、YouTubeの勉強用BGMチャンネル「ポモドーロ書斎」を運営しています。</p>
<div class="channel">
  {icon("youtube", "channel__mark")}
  <div class="channel__info">
    <p class="channel__label">OUR CHANNEL</p>
    <p class="channel__name">ポモドーロ書斎</p>
    <p class="channel__handle">@pomodoro.shosai</p>
    <p class="channel__desc">勉強の時間に流せる、勉強用BGMを公開しているYouTubeチャンネルです。</p>
    <p class="channel__link"><a class="btn btn--ink" href="{YOUTUBE}" target="_blank" rel="noopener">YouTubeでチャンネルを見る{NEWTAB}</a></p>
    <p class="channel__url">{YOUTUBE}</p>
  </div>
</div>"""),
]

STANCE = [
    ("広告を隠さない", "広告を含む発信には、広告であることを分かりやすく表示します。報酬の有無や金額で、内容の評価を変えません。"),
    ("AIまかせにしない", "生成AIは制作の道具として使います。公開する前に、事実・権利・表現を人が確認します。"),
    ("盛らない", "根拠の分からない数字や、実際よりよく見せる表現は使いません。分からないことは、分からないと伝えます。"),
]

PAGES = [
    dict(file="privacy.html", src="privacy.md", h1="プライバシーポリシー", en="PRIVACY POLICY", color="cyan",
         title=f"プライバシーポリシー｜{CORP}",
         desc=f"{CORP}のプライバシーポリシーです。Webサイト（mogamii.com）や、SNS・YouTube・Webメディアなどでの情報発信における、個人情報やCookieなどの取り扱いについて定めています。",
         lead="当社のWebサイトや、SNS・YouTube・Webメディアなどでの情報発信における、個人情報やCookieなどの取り扱いについて定めています。"),
    dict(file="disclaimer.html", src="disclaimer.md", h1="広告掲載について・免責事項", en="DISCLAIMER", color="plain",
         title=f"広告掲載について・免責事項｜{CORP}",
         desc=f"{CORP}の広告掲載の方針（アフィリエイトプログラムへの参加、ステルスマーケティング規制への対応）と、掲載情報・リンク・著作権についての免責事項です。",
         lead="広告掲載の方針と、掲載情報・リンク・著作権についての考え方をまとめています。"),
    dict(file="contact.html", src="contact.md", h1="お問い合わせ", en="CONTACT", color="pink",
         title=f"お問い合わせ｜{CORP}",
         desc=f"{CORP}へのお問い合わせ窓口です。お問い合わせは、メールで受け付けています。",
         lead="当社へのお問い合わせは、メールで受け付けています。"),
]

NAV = [("home", "", "トップ"), ("services", "services.html", "事業内容"),
       ("company", "company.html", "会社概要"), ("contact", "contact.html", "お問い合わせ")]
MARQUEE_TOP = ["WEB MEDIA", "Webメディア", "SNS", "情報発信", "GENERATIVE AI", "生成AIでつくる",
               "YOUTUBE", "ポモドーロ書斎", "MOGAMII", "つくる・とどける・つづける"]


# ---------------------------------------------------------------- 共通パーツ
def head(title, desc, path, p, extra=""):
    canon = f"{SITE}/{path}"
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{CORP}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="ja_JP">
<meta property="og:image" content="{SITE}/assets/ogp.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#fbf4e4">
{extra}<link rel="icon" href="{p}favicon.ico" sizes="32x32">
<link rel="icon" href="{p}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{p}apple-touch-icon.png">
<link rel="preload" href="{p}assets/fonts/zen-kaku-gothic-new-900.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{p}assets/style.css">
</head>"""


def home(p):
    """トップページへのリンク先。URLに index.html を出さない（/ で開く）。"""
    return p or "./"


def marquee(items):
    def cls(t):
        return "marquee__item" if t.isascii() else "marquee__item marquee__item--ja"

    seq = "".join(f'<span class="{cls(t)}">{t}</span><span class="marquee__sep">★</span>' for t in items * 2)
    return (f'<div class="marquee" aria-hidden="true"><div class="marquee__track">'
            f'<div class="marquee__group">{seq}</div><div class="marquee__group">{seq}</div></div></div>')


def logo(p, mod=""):
    return (f'<a class="logo {mod}" href="{home(p)}">{LOGO}<span class="logo__text">'
            f'<span class="logo__word">Mogamii</span><span class="logo__tag">合同会社</span></span></a>')


def header(p, current):
    lis = []
    for key, href, label in NAV:
        cur = ' aria-current="page"' if key == current else ""
        cls = {"home": ' class="gnav__home"', "contact": ' class="gnav__cta"'}.get(key, "")
        lis.append(f'<li{cls}><a href="{home(p) if key == "home" else p + href}"{cur}>{label}</a></li>')
    return f"""<div class="adbar"><p>{AD_NOTICE}<a href="{p}disclaimer.html#ad">広告掲載について</a></p></div>
<header class="site-header">
  <div class="container site-header__inner">
    {logo(p)}
    <nav class="gnav" aria-label="メインメニュー"><ul>{"".join(lis)}</ul></nav>
  </div>
</header>"""


def footer(p):
    return f"""<footer class="site-footer">
  <div class="container footer-grid">
    <div class="footer-brand">
      {logo(p, "logo--footer")}
      <p>Webメディア・SNS運営、生成AIを活用したコンテンツ制作、YouTubeチャンネル運営を行っています。</p>
    </div>
    <nav class="footer-nav" aria-label="フッターメニュー">
      <p class="footer-h">MENU</p>
      <ul>
        <li><a href="{home(p)}">トップ</a></li>
        <li><a href="{p}services.html">事業内容</a></li>
        <li><a href="{p}company.html">会社概要</a></li>
        <li><a href="{p}contact.html">お問い合わせ</a></li>
        <li><a href="{p}privacy.html">プライバシーポリシー</a></li>
        <li><a href="{p}disclaimer.html">広告掲載について・免責事項</a></li>
      </ul>
    </nav>
    <div class="footer-company">
      <p class="footer-h">COMPANY</p>
      <dl>
        <div><dt>会社名</dt><dd>{CORP}</dd></div>
        <div><dt>所在地</dt><dd>{COMPANY["area"]}</dd></div>
        <div><dt>お問い合わせ</dt><dd><a href="mailto:{EMAIL}">{EMAIL_WBR}</a></dd></div>
      </dl>
    </div>
  </div>
  <div class="container footer-bottom">
    <p class="footer-pr"><span class="pr-badge">PR</span>{AD_NOTICE}広告を含む発信では、その旨を表示します。詳しくは<a href="{p}disclaimer.html#ad">広告掲載について</a>をご覧ください。</p>
    <p class="copyright"><small>© 2026 {CORP}</small></p>
  </div>
</footer>"""


def doc(head_html, p, current, main_html):
    return f"""{head_html}
<body>
<a class="skip-link" href="#main">本文へスキップ</a>
{header(p, current)}
<main id="main">
{main_html}
</main>
{footer(p)}
</body>
</html>
"""


def breadcrumb(items):
    lis = "".join(f'<li><a href="{h}">{t}</a></li>' if h else f'<li aria-current="page">{t}</li>'
                  for h, t in items)
    return f'<nav class="breadcrumb" aria-label="パンくずリスト"><ol>{lis}</ol></nav>'


def page_hero(color, crumbs, en, h1, lead):
    return f"""<header class="page-hero page-hero--{color}">
  <div class="container">
    {breadcrumb(crumbs)}
    <p class="page-hero__en" aria-hidden="true">{en}</p>
    <h1 class="page-hero__title">{h1}</h1>
    <p class="page-hero__lead">{lead}</p>
  </div>
</header>"""


def section_head(en, title, hid, lead=""):
    lead_html = f'\n      <p class="lead">{lead}</p>' if lead else ""
    return f"""<div class="section-head">
      <p class="eyebrow" aria-hidden="true">{en}</p>
      <h2 class="section-title" id="{hid}">{title}</h2>{lead_html}
    </div>"""


def cta_section():
    return f"""<section class="section section--cta" aria-labelledby="cta-title">
  <div class="container">
    <div class="cta-box">
      <div>
        <p class="eyebrow" aria-hidden="true">CONTACT</p>
        <h2 class="section-title" id="cta-title">お問い合わせ</h2>
        <p class="cta-box__text">{CORP}へのお問い合わせは、メールで受け付けています。お問い合わせの前に、<a href="contact.html">お問い合わせページ</a>のご案内もご覧ください。</p>
      </div>
      <p><a class="btn btn--mail" href="mailto:{EMAIL}">{EMAIL_WBR}</a></p>
    </div>
  </div>
</section>"""


def stance_section():
    lis = "".join(f"<li><h3>{t}</h3><p>{d}</p></li>" for t, d in STANCE)
    return f"""<section class="section" aria-labelledby="stance-title">
  <div class="container">
    {section_head("OUR STANCE", "3つの事業に共通する考え方", "stance-title")}
    <ol class="stance">{lis}</ol>
  </div>
</section>"""


EQ_BARS = [38, 62, 48, 80, 56, 92, 70, 44, 84, 60, 96, 52, 74, 40, 66, 88, 50, 72, 36, 58]
ARROW = '<span class="btn__arrow" aria-hidden="true">→</span>'


# ---------------------------------------------------------------- ページ本体
def index_main():
    biz = "".join(f"""<li class="cat cat--{s["color"]}">
        <div class="cat__top">{icon(s["id"], "cat__icon")}<p class="cat__num" aria-hidden="true">{s["num"]}</p></div>
        <p class="cat__en" aria-hidden="true">{E(s["en"])}</p>
        <h3 class="cat__name"><a href="services.html#{s["id"]}">{s["name"]}</a></h3>
        <p class="cat__desc">{s["card"]}</p>
        <p class="cat__more" aria-hidden="true">くわしく見る <span>→</span></p>
      </li>""" for s in SERVICES)
    bars = "".join(f'<span style="--h:{h}%;--d:-{(k * 0.37) % 1.8:.2f}s"></span>' for k, h in enumerate(EQ_BARS))
    star = (f'<svg class="poster__star" viewBox="0 0 200 200" focusable="false">'
            f'<polygon class="poster__burst" points="{burst_points(24, 96, 82, 100, 100)}" fill="#ff2e88" '
            'stroke="#15130f" stroke-width="3" stroke-linejoin="round"/>'
            '<circle cx="100" cy="100" r="56" fill="#fff" stroke="#15130f" stroke-width="3"/>'
            '<path d="M71 129V73l29 31 29-31v56" fill="none" stroke="#15130f" stroke-width="13" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return f"""<section class="hero" aria-labelledby="hero-title">
  <div class="container hero__inner">
    <div class="hero__copy">
      <h1 class="hero__title" id="hero-title"><span class="hero__name">{CORP}</span><span class="hero__line">つくる。</span><span class="hero__line"><span class="hero__mark">とどける。</span></span><span class="hero__line">つづける。</span></h1>
      <p class="hero__lead">SNS・Webメディアでの情報発信、生成AIを活用したコンテンツ制作、YouTubeチャンネルの運営を行う、{COMPANY["area"]}の会社です。2024年8月に設立しました。</p>
      <ul class="hero__actions">
        <li><a class="btn btn--pink" href="services.html">事業内容を見る{ARROW}</a></li>
        <li><a class="btn" href="company.html">会社概要を見る{ARROW}</a></li>
      </ul>
    </div>
    <div class="hero__art" aria-hidden="true">
      <div class="poster">
        <span class="poster__tag poster__tag--tl">EST. 2024</span>
        <span class="poster__tag poster__tag--tr">YOKOHAMA</span>
        {star}
        <ul class="poster__chips"><li>Webメディア・SNS</li><li>生成AI</li><li>YouTube</li></ul>
      </div>
    </div>
  </div>
</section>
{marquee(MARQUEE_TOP)}
<section class="section" aria-labelledby="biz-title">
  <div class="container">
    {section_head("BUSINESS", "事業内容", "biz-title", "3つの事業で、コンテンツをつくり、とどけています。")}
    <ul class="cats">
      {biz}
    </ul>
  </div>
</section>
<section class="section feature" aria-labelledby="ch-title">
  <div class="container feature__inner">
    <div>
      <p class="eyebrow" aria-hidden="true">OUR CHANNEL</p>
      <h2 class="section-title" id="ch-title">ポモドーロ書斎</h2>
      <p class="feature__handle">@pomodoro.shosai</p>
      <p class="feature__desc">勉強の時間に流せる、勉強用BGMを公開しているYouTubeチャンネルです。自社で運営しています。</p>
      <p><a class="btn btn--yellow" href="{YOUTUBE}" target="_blank" rel="noopener">YouTubeでチャンネルを見る<span class="sr-only">（新しいタブで開きます）</span><span class="btn__arrow" aria-hidden="true">↗</span></a></p>
    </div>
    <div class="player" aria-hidden="true">
      <div class="player__screen">{bars}</div>
      <div class="player__meta"><span class="player__icon">♪</span><div><p class="player__name">ポモドーロ書斎</p><p class="player__sub">STUDY BGM / YOUTUBE</p></div></div>
      <div class="player__bar"></div>
    </div>
  </div>
</section>
{stance_section()}
<section class="section company" aria-labelledby="co-title">
  <div class="container company__inner">
    {section_head("COMPANY", "会社概要", "co-title")}
    <div>
      <dl class="facts">
        <div><dt>会社名</dt><dd>{CORP}</dd></div>
        <div><dt>設立</dt><dd><time datetime="{COMPANY["founded_iso"]}">{COMPANY["founded"]}</time></dd></div>
        <div><dt>所在地</dt><dd>{COMPANY["area"]}</dd></div>
      </dl>
      <p class="company__cta"><a class="text-link" href="company.html">会社概要を見る<span aria-hidden="true"> →</span></a></p>
    </div>
  </div>
</section>
{cta_section()}"""


def services_main():
    jump = "".join(f'<li><a class="sticker sticker--{s["color"]}" href="#{s["id"]}">{s["num"]} {s["name"]}</a></li>'
                   for s in SERVICES)
    secs = "".join(f"""<section class="svc svc--{s["color"]}" id="{s["id"]}" aria-labelledby="h-{s["id"]}">
  <div class="svc__head">
    <p class="svc__num" aria-hidden="true">{s["num"]}</p>
    {icon(s["id"], "svc__icon")}
    <p class="svc__en" aria-hidden="true">{s["en"]}</p>
    <h2 class="svc__title" id="h-{s["id"]}">{s["name"]}</h2>
  </div>
  <div class="svc__body">
{s["body"]}
  </div>
</section>""" for s in SERVICES)
    hero = page_hero("pink", [("./", "トップ"), (None, "事業内容")], "SERVICES", "事業内容",
                     f"{CORP}は、次の3つの事業を行っています。")
    return f"""{hero}
<nav class="jump container" aria-label="このページの事業一覧"><ul>{jump}</ul></nav>
<div class="container svc-list">
{secs}
</div>
{stance_section()}
{cta_section()}"""


def company_main():
    biz = "".join(f'<li><a href="services.html#{s["id"]}">{s["name"]}</a>'
                  + ("（勉強用BGMチャンネル「ポモドーロ書斎」）" if s["id"] == "youtube" else "") + "</li>"
                  for s in SERVICES)
    rows = [
        ("会社名", CORP),
        ("設立", f'<time datetime="{COMPANY["founded_iso"]}">{COMPANY["founded"]}</time>'),
        ("所在地", COMPANY["area"]),
        ("事業内容", f'<ul class="company-biz">{biz}</ul>'),
        ("お問い合わせ", f'<a href="mailto:{EMAIL}">{EMAIL_WBR}</a>'),
        ("URL", COMPANY["url"]),
    ]
    trs = "".join(f'<tr><th scope="row">{k}</th><td>{v}</td></tr>' for k, v in rows)
    hero = page_hero("yellow", [("./", "トップ"), (None, "会社概要")], "COMPANY", "会社概要",
                     f"{CORP}の会社情報です。")
    return f"""{hero}
<div class="page-body"><div class="prose">
<h2 id="info">会社情報</h2>
<div class="table-wrap table-wrap--company"><table class="company-table"><caption class="sr-only">{CORP}の会社情報</caption><tbody>{trs}</tbody></table></div>
<h2 id="channel">運営しているYouTubeチャンネル</h2>
<p>当社は、勉強用BGMチャンネル「ポモドーロ書斎」（@pomodoro.shosai）を運営しています。</p>
<p class="company-link"><a class="btn btn--ink" href="{YOUTUBE}" target="_blank" rel="noopener">YouTubeで「ポモドーロ書斎」を見る{NEWTAB}</a></p>
<h2 id="links">関連ページ</h2>
<ul class="link-stickers">
  <li><a class="sticker sticker--pink" href="services.html">事業内容</a></li>
  <li><a class="sticker sticker--yellow" href="contact.html">お問い合わせ</a></li>
  <li><a class="sticker sticker--cyan" href="privacy.html">プライバシーポリシー</a></li>
  <li><a class="sticker" href="disclaimer.html">広告掲載について・免責事項</a></li>
</ul>
</div></div>
{cta_section()}"""


def notfound_main():
    return """<section class="notfound">
  <div class="container">
    <p class="notfound__num" aria-hidden="true">404</p>
    <h1 class="notfound__title">ページが見つかりませんでした</h1>
    <p>お探しのページは、移動または削除された可能性があります。URLに誤りがないかご確認ください。</p>
    <ul class="notfound__links">
      <li><a class="sticker sticker--yellow" href="/">トップページへ</a></li>
      <li><a class="sticker sticker--pink" href="/services.html">事業内容</a></li>
      <li><a class="sticker sticker--cyan" href="/company.html">会社概要</a></li>
      <li><a class="sticker" href="/contact.html">お問い合わせ</a></li>
    </ul>
  </div>
</section>"""


# ---------------------------------------------------------------- 出力
def clean_out():
    """public/ を空にして作り直し、src/assets/ をコピーする。"""
    if OUT.resolve() != (ROOT / "public").resolve() or OUT.resolve() == ROOT.resolve():
        raise SystemExit(f"出力先が想定外です: {OUT}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    if ASSETS.is_dir():
        shutil.copytree(ASSETS, OUT / "assets", ignore=shutil.ignore_patterns("root"))
        for f in sorted((ASSETS / "root").glob("*")):  # favicon.ico など、サイト直下に置くファイル
            if f.is_file():
                shutil.copy2(f, OUT / f.name)


def write(rel, text):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def font_coverage_note():
    """見出し用フォントに入っていない文字があれば知らせる（表示はできるので、止めはしない）。"""
    chars_file = ROOT / "src" / "fonts" / "chars.txt"
    if not chars_file.is_file():
        print("注意: src/fonts/chars.txt がありません。python3 src/subset_fonts.py を実行してください。")
        return
    have = set(chars_file.read_text(encoding="utf-8"))
    used = set()
    for f in OUT.glob("*.html"):
        used |= set(re.sub(r"<[^>]+>", "", f.read_text(encoding="utf-8")))
    missing = sorted(c for c in used - have if not c.isspace())
    if missing:
        print(f"注意: 見出し用フォントに無い文字が {len(missing)} 個あります: {''.join(missing)}")
        print("      python3 src/subset_fonts.py を実行して、フォントを作り直してください。")


def main():
    clean_out()
    write("index.html", doc(head(f"{CORP}｜Webメディア・SNS運営、生成AIコンテンツ制作、YouTubeチャンネル運営",
                                 f"{CORP}（{COMPANY['area']}）の公式サイトです。Webメディア・SNS運営、生成AIを活用したコンテンツ制作、YouTubeの勉強用BGMチャンネル「ポモドーロ書斎」の運営を行っています。",
                                 "", ""), "", "home", index_main()))
    write("services.html", doc(head(f"事業内容｜{CORP}",
                                    f"{CORP}の事業内容。Webメディア・SNS運営（アフィリエイトプログラムを含む広告による収益化）、生成AIを活用したコンテンツ制作、YouTubeチャンネル「ポモドーロ書斎」の運営について紹介します。",
                                    "services.html", ""), "", "services", services_main()))
    write("company.html", doc(head(f"会社概要｜{CORP}",
                                   f"{CORP}の会社概要。設立日、所在地（{COMPANY['area']}）、事業内容、お問い合わせ先を掲載しています。",
                                   "company.html", ""), "", "company", company_main()))
    for pg in PAGES:
        body = add_ids(md((SRC / "pages" / pg["src"]).read_text(encoding="utf-8")))
        hero = page_hero(pg["color"], [("./", "トップ"), (None, pg["h1"])], pg["en"], pg["h1"], pg["lead"])
        main_html = f'{hero}\n<div class="page-body"><div class="prose">\n{body}\n</div></div>'
        write(pg["file"], doc(head(pg["title"], pg["desc"], pg["file"], ""), "", pg["file"][:-5], main_html))
    write("404.html", doc(head(f"ページが見つかりませんでした｜{CORP}",
                               f"お探しのページは見つかりませんでした。{CORP}のトップページからお探しください。",
                               "404.html", "/", extra='<meta name="robots" content="noindex">\n'),
                          "/", "", notfound_main()))
    write("favicon.svg", FAVICON)
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    urls = ["", "services.html", "company.html", "contact.html", "privacy.html", "disclaimer.html"]
    items = "".join(f"  <url>\n    <loc>{SITE}/{u}</loc>\n    <lastmod>{TODAY}</lastmod>\n  </url>\n" for u in urls)
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{items}</urlset>\n')
    font_coverage_note()
    print("生成したファイル:")
    for f in sorted(OUT.rglob("*")):
        if f.is_file():
            print(f"  public/{f.relative_to(OUT).as_posix()}  ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
