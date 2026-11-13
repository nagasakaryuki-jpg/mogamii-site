#!/usr/bin/env python3
"""public/ を検査する（コーポレートサイト構成）。使い方: python3 src/check.py

検査すること
- 想定どおりのページだけがあること（articles/・about.html などの旧ページが残っていないこと）
- 内部リンク・アンカーの切れ、articles/ や about.html への参照がないこと
- 外部リソース（CDN・外部フォント・画像など）の読み込み、script・iframe・インラインJSがないこと
- 外部リンクは許可したものだけで、rel="noopener" が付いていること
- 住所の番地・区名・郵便番号・電話番号、指定外のメールアドレスが混入していないこと
- 全ページに広告表記（ページ上部の帯とフッター）があること
- 必須タグ（lang・title・description・canonical・OGP）と、sitemap.xml・robots.txt の内容
"""
import html
import pathlib
import re
import sys
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

ROOT = pathlib.Path(__file__).resolve().parent.parent / "public"
SITE = "https://mogamii.com/"
EMAIL = "info@mogamii.com"
AREA = "神奈川県横浜市"
ALLOWED_EXTERNAL = {"https://www.youtube.com/@pomodoro.shosai"}

# 現存ページ（これ以外の HTML があればエラー）
PAGES = ["index.html", "services.html", "company.html", "contact.html", "privacy.html", "disclaimer.html"]
EXPECTED_HTML = set(PAGES) | {"404.html"}
SITEMAP_URLS = {SITE + ("" if p == "index.html" else p) for p in PAGES}
TEXT_SUFFIXES = {".html", ".xml", ".txt", ".css", ".svg"}

AD_TEXT = "アフィリエイト広告が含まれる場合があります"
SEP = r"[-‐‑–—―ー－ ]"
FORBIDDEN = [
    # 旧構成への参照
    (r"articles/", "articles/ への参照がある"),
    (r"about\.html", "about.html への参照がある"),
    # 電話番号
    (r"(?<![\d.])(?:0\d{1,4}|\+81" + SEP + r"?\d{1,4})" + SEP + r"?[(（]?\d{1,4}[)）]?" + SEP + r"\d{3,4}(?!\d)",
     "電話番号らしき文字列がある"),
    (r"(?<![\d.])0\d{9,10}(?![\d.])", "電話番号らしき数字の並びがある"),
    (r"電話番号|TEL|FAX", "電話番号の項目がある"),
    # 所在地（神奈川県横浜市より細かい情報）
    (r"横浜市\s*[^\s<、。，．」）)]{1,6}区", "横浜市の区名以降の所在地がある"),
    (r"(?:鶴見|神奈川|保土[ケヶが]谷|磯子|金沢|港北|戸塚|港南|瀬谷|青葉|都筑|西|中|南|旭|緑|栄|泉)区",
     "横浜市の区名がある"),
    (r"\d+丁目|\d+番地|\d+番\d+号|(?<![\d-])\d{1,3}-\d{1,3}-\d{1,3}(?![\d-])", "番地らしき文字列がある"),
    (r"〒|(?<![\d-])\d{3}-\d{4}(?![\d-])", "郵便番号らしき文字列がある"),
    # 与えられていない事実・使わない表現
    (r"資本金|従業員数|社員数|売上|取引先|顧客数|登録者数|フォロワー数|再生回数|受賞",
     "与えられていない事実（資本金・従業員数・登録者数など）の項目がある"),
    (r"必ず|絶対|【要確認】", "使わない表現（「必ず」「絶対」「【要確認】」）がある"),
    (r"記事", "記事メディア前提の文言（「記事」）がある"),
]

# ページごとに入っているべき文言
REQUIRED_TEXT = {
    "privacy.html": ["取得する情報", "利用目的", "Cookie", "アクセス解析", "アフィリエイトプログラム", "第三者",
                     "安全管理", "開示", "改定", EMAIL, "制定日：2026年11月13日"],
    "disclaimer.html": ["アフィリエイトプログラムに参加しています", "景品表示法", "ステルスマーケティング",
                        "2023年10月1日", "「PR」", "「広告」", "掲載情報の正確性", "リンク先", "著作権"],
    "contact.html": [f'href="mailto:{EMAIL}"', "返信までの期間はお約束できません", "営業"],
    "404.html": ['name="robots" content="noindex"'],
}


class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.refs, self.tags, self.meta, self.links, self.handlers = set(), [], [], {}, [], []
        self.lang = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta[key] = a.get("content", "")
        if tag == "link":
            self.links.append(a)
        self.handlers += [k for k in a if k.startswith("on")]
        for attr in ("href", "src", "poster", "action", "data", "formaction"):
            if a.get(attr):
                self.refs.append((tag, attr, a[attr], a))
        if a.get("srcset"):
            for part in a["srcset"].split(","):
                if part.strip():
                    self.refs.append((tag, "srcset", part.split()[0], a))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def scan(path):
    s = Scan()
    s.feed(path.read_text(encoding="utf-8"))
    return s


def plain(text):
    """禁止要素を探すための文字列。SVGの座標を除き、実体参照を戻し、全角英数を半角にそろえる。"""
    text = re.sub(r"<svg\b.*?</svg>", " ", text, flags=re.S)
    text = text.replace("<wbr>", "")
    return unicodedata.normalize("NFKC", html.unescape(text))


def check_refs(p, s, parsed, errors, external):
    rel = p.relative_to(ROOT).as_posix()
    for tag, attr, url, a in s.refs:
        if tag == "link" and a.get("rel") == "canonical":
            continue  # canonical は別に検証する（読み込みではない）
        parts = urlsplit(url)
        if parts.scheme in ("http", "https") or (not parts.scheme and parts.netloc):
            external.add(url)
            if tag != "a":
                errors.append(f"{rel}: 外部リソースを読み込んでいる <{tag} {attr}> {url}")
                continue
            if "noopener" not in (a.get("rel") or ""):
                errors.append(f"{rel}: 外部リンクに rel=noopener がない {url}")
            if url not in ALLOWED_EXTERNAL:
                errors.append(f"{rel}: 許可していない外部リンク {url}")
            continue
        if parts.scheme == "mailto":
            if url != f"mailto:{EMAIL}":
                errors.append(f"{rel}: 想定外の mailto {url}")
            continue
        if parts.scheme:
            errors.append(f"{rel}: 想定外のスキーム {url}")
            continue
        if url.startswith("/"):
            target = ROOT / unquote(parts.path).lstrip("/")
        elif parts.path:
            target = (p.parent / unquote(parts.path)).resolve()
        else:
            target = p
        if target.is_dir() or parts.path.endswith("/"):
            target = target / "index.html"
        try:
            target.resolve().relative_to(ROOT)
        except ValueError:
            errors.append(f"{rel}: public/ の外を参照している {url}")
            continue
        if not target.exists():
            errors.append(f"{rel}: リンク切れ {url}")
            continue
        if parts.fragment and target.suffix == ".html":
            tgt = parsed.get(target.resolve()) or scan(target)
            if parts.fragment not in tgt.ids:
                errors.append(f"{rel}: アンカー切れ {url}")


def check_page(p, s, errors):
    rel = p.relative_to(ROOT).as_posix()
    text = p.read_text(encoding="utf-8")
    # ---- 必須タグ
    if s.lang != "ja":
        errors.append(f"{rel}: html lang が ja ではない")
    if not s.title.strip():
        errors.append(f"{rel}: title なし")
    for key in ("viewport", "description", "og:title", "og:description", "og:url", "og:type", "og:site_name"):
        if not s.meta.get(key):
            errors.append(f"{rel}: meta {key} なし")
    canon = [l.get("href", "") for l in s.links if l.get("rel") == "canonical"]
    if len(canon) != 1 or not canon[0].startswith(SITE):
        errors.append(f"{rel}: canonical 不正 {canon}")
    elif s.meta.get("og:url") != canon[0]:
        errors.append(f"{rel}: og:url と canonical が不一致")
    # ---- JS を使わない
    if {"script", "iframe", "object", "embed"} & set(s.tags):
        errors.append(f"{rel}: script/iframe/object/embed が含まれる")
    if s.handlers:
        errors.append(f"{rel}: インラインのイベント属性がある {sorted(set(s.handlers))}")
    if re.search(r"url\(\s*['\"]?(?:https?:)?//|@import", text):
        errors.append(f"{rel}: style で外部リソースを読み込んでいる")
    # ---- 広告表記（ページ上部の帯とフッターの両方）
    bar = re.search(r'<div class="adbar">(.*?)</div>', text, re.S)
    if not bar or AD_TEXT not in bar.group(1) or "disclaimer.html#ad" not in bar.group(1):
        errors.append(f"{rel}: ページ上部の広告表記（{AD_TEXT}）または広告掲載についてへのリンクがない")
    foot = re.search(r'<p class="footer-pr">(.*?)</p>', text, re.S)
    if not foot or AD_TEXT not in foot.group(1) or '<span class="pr-badge">PR</span>' not in foot.group(1):
        errors.append(f"{rel}: フッターの広告表記（PR表示）がない")
    if "© 2026 Mogamii合同会社" not in text:
        errors.append(f"{rel}: コピーライト表記がない")
    # ---- 共通メニュー
    for page in PAGES:
        if not re.search(r'href="[^"]*' + re.escape(page) + r'(?:#[^"]*)?"', text):
            errors.append(f"{rel}: {page} へのリンクがない")
    # ---- 所在地は「神奈川県横浜市」まで、連絡先は指定のメールアドレスだけ
    for v in re.findall(r"所在地</(?:dt|th)>\s*<(?:dd|td)>(.*?)</(?:dd|td)>", text, re.S):
        if v.strip() != AREA:
            errors.append(f"{rel}: 所在地が「{AREA}」ではない（{v.strip()}）")
    for mail in set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", plain(text))):
        if mail != EMAIL:
            errors.append(f"{rel}: 想定外のメールアドレス {mail}")
    for must in REQUIRED_TEXT.get(rel, []):
        if must not in text:
            errors.append(f"{rel}: 「{must}」がない")


def main():
    errors = []
    if not ROOT.is_dir():
        print("NG: public/ がありません。先に python3 src/build.py を実行してください。")
        return 1
    files = sorted(f for f in ROOT.rglob("*") if f.is_file())
    pages = [f for f in files if f.suffix == ".html"]
    parsed = {p: scan(p) for p in pages}
    external = set()
    # ---- ページ構成（旧ページが残っていないこと）
    found = {p.relative_to(ROOT).as_posix() for p in pages}
    for miss in sorted(EXPECTED_HTML - found):
        errors.append(f"{miss} がない")
    for extra in sorted(found - EXPECTED_HTML):
        errors.append(f"想定外のページが残っている public/{extra}")
    if (ROOT / "articles").exists():
        errors.append("public/articles/ が残っている")
    # ---- 全テキストファイルの禁止要素
    for f in files:
        if f.suffix not in TEXT_SUFFIXES:
            continue
        rel = f.relative_to(ROOT).as_posix()
        text = plain(f.read_text(encoding="utf-8"))
        for pat, why in FORBIDDEN:
            hit = re.search(pat, text)
            if hit:
                errors.append(f"{rel}: {why}（{hit.group(0)}）")
        if f.suffix in (".css", ".svg") and re.search(r"url\(\s*['\"]?(?:https?:)?//|@import|<script|href=\"http", text):
            errors.append(f"{rel}: 外部リソースの読み込みやスクリプトがある")
    # ---- HTML ごとの検査
    for p, s in parsed.items():
        check_page(p, s, errors)
        check_refs(p, s, parsed, errors, external)
    # ---- sitemap.xml（現存ページのみ）
    sm_path = ROOT / "sitemap.xml"
    locs = re.findall(r"<loc>(.*?)</loc>", sm_path.read_text(encoding="utf-8")) if sm_path.exists() else []
    if not sm_path.exists():
        errors.append("sitemap.xml がない")
    if len(locs) != len(set(locs)):
        errors.append("sitemap: URL が重複している")
    for loc in sorted(set(locs) - SITEMAP_URLS):
        errors.append(f"sitemap: 現存ページ以外の URL がある {loc}")
    for loc in sorted(SITEMAP_URLS - set(locs)):
        errors.append(f"sitemap: 現存ページの URL がない {loc}")
    # ---- robots.txt
    rb_path = ROOT / "robots.txt"
    rb = rb_path.read_text(encoding="utf-8") if rb_path.exists() else ""
    if f"Sitemap: {SITE}sitemap.xml" not in rb:
        errors.append("robots.txt: Sitemap の指定がない")
    if re.search(r"^Disallow:\s*/\s*$", rb, re.M):
        errors.append("robots.txt: サイト全体をクロール禁止にしている")
    # ---- 結果
    print(f"HTML {len(pages)} ファイルを検査:", " ".join(sorted(found)))
    print(f"sitemap.xml {len(locs)} URL:", " ".join(locs))
    print("外部リンク:", *(sorted(external) or ["なし"]), sep="\n  ")
    for e in errors:
        print("NG:", e)
    print("結果:", "OK" if not errors else f"{len(errors)} 件の問題")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
