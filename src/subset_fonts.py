#!/usr/bin/env python3
"""見出し用フォントを、サイトで使う文字だけに絞って src/assets/fonts/ に作り直す。

使い方: python3 src/build.py && python3 src/subset_fonts.py && python3 src/build.py
        （1回目のビルドで文字を集め、フォントを作り、2回目のビルドで public/ に入れる）
必要なもの: pip install fonttools brotli
元のフォント（SIL Open Font License 1.1）は src/fonts/ にある。
"""
import pathlib
import re
import string

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
FONTS_SRC = ROOT / "src" / "fonts"
FONTS_OUT = ROOT / "src" / "assets" / "fonts"
ASCII = string.ascii_letters + string.digits + string.punctuation + " "
EXTRA = "→↗←↑↓★♪©×・「」『』（）、。：；！？〜ー…％＆＠"


def site_chars():
    chars = set(ASCII) | set(EXTRA)
    pages = sorted(PUBLIC.glob("*.html"))
    if not pages:
        raise SystemExit("public/ にHTMLがありません。先に python3 src/build.py を実行してください。")
    for f in pages:
        text = re.sub(r"<(script|style)\b.*?</\1>", "", f.read_text(encoding="utf-8"), flags=re.S)
        chars |= set(re.sub(r"<[^>]+>", "", text))
    return "".join(sorted(c for c in chars if not c.isspace() or c == " "))


def make(src_name, out_name, text):
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.drop_tables += ["DSIG"]
    font = TTFont(FONTS_SRC / src_name)
    sub = subset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    out = FONTS_OUT / out_name
    font.flavor = "woff2"
    font.save(out)
    print(f"  {out.relative_to(ROOT)}  ({out.stat().st_size:,} bytes)")


def main():
    FONTS_OUT.mkdir(parents=True, exist_ok=True)
    text = site_chars()
    print(f"文字数: {len(text)}")
    make("ZenKakuGothicNew-Black.ttf", "zen-kaku-gothic-new-900.woff2", text)
    make("ArchivoBlack-Regular.ttf", "archivo-black.woff2", ASCII)
    (FONTS_SRC / "chars.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
