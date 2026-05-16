"""
CFA Society Japan ブログのスクレイパー。

対象 URL: https://www.cfasociety.org/japan/society-news-resources/blog
プラットフォーム: Higher Logic + Cloudflare CDN

listing には No.XXX のエントリが時系列(新→旧)で並ぶ。各エントリのリンクテキスト
は固定の prefix を持つ:

    [No.760 CFA協会ブログ4-16-2026] 市場の現実ではなく、商品の機能としての流動性

prefix 内訳:
  - 開きかぎ括弧(半角 `[` または全角 `［`)
  - "No"(末尾の `.` 有/無 揺れ、`.` の後の空白も揺れ)
  - 番号(任意桁)
  - "CFA協会ブログ"(稀に typo "CFA協会ブロブ")
  - 日付 M-D-YYYY(月日は zero pad 有/無、区切りは `-`)
  - 閉じかぎ括弧(`]` / `］`)

タイトル本体は閉じ括弧の後の文字列。

記事 URL は `https://www.cfasociety.org/japan/society-news-resources/blog/<番号>`。
末尾スラッシュ有り/無し両対応。

古い記事(No.557 以前)は本文ページではなく S3 直リンクの PDF を指す。これらは
URL pattern が一致しないため自動的に除外される(`/japan/society-news-resources/`
パスは S3 URL には含まれない)。30 日 prune の対象外でもあるので実害なし。

同一行に2リンク(タイトル付き + URL そのものをリンクテキストにしたもの)が並ぶ
レイアウトに対応する必要がある。`extract_listing_links` の「最長テキスト」戦略
だと短いタイトルでは URL のほうが長くなり broken になるため、本アダプターは
自前で anchor walk + prefix regex match による絞り込みを行う。

更新履歴:
- 2026-05-16 (update-016): 初版
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .scrape_base import ScrapeAdapterBase, parse_jp_date


# 記事 URL: /japan/society-news-resources/blog/<数字>(末尾スラッシュ有/無 両対応)
_ARTICLE_RE = re.compile(
    r"^https?://(?:www\.)?cfasociety\.org"
    r"/japan/society-news-resources/blog/\d+/?$",
    re.IGNORECASE,
)

# listing リンクテキスト先頭の固定 prefix
#   半角・全角の角括弧、No の `.` の有無、ブログ/ブロブ、日付の zero pad 有無、
#   "ブログ" と日付の間の空白の有無、全てに対応する。
_TITLE_PREFIX_RE = re.compile(
    r"^\s*[\[\［]\s*"
    r"No\.?\s*\d+\s*"
    r"CFA協会ブロ[グブ]\s*"
    r"(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})"
    r"\s*[\]\］]\s*"
)


class CFAJapanAdapter(ScrapeAdapterBase):
    source_type = "scrape_cfajapan"

    def parse_listing(self, soup: BeautifulSoup, base_url: str, feed: dict) -> list[dict]:
        items = []
        seen_urls = set()
        for a in soup.find_all("a", href=True):
            absolute = urljoin(base_url, a["href"])
            if not _ARTICLE_RE.match(absolute):
                continue
            # 末尾スラッシュを除去して canonical URL に正規化
            absolute = absolute.rstrip("/")
            if absolute in seen_urls:
                continue
            text = a.get_text(strip=True)
            # 同一行 dup anchor 対策: テキストが URL そのものになっている方は無視
            if text.startswith("http://") or text.startswith("https://"):
                continue
            m = _TITLE_PREFIX_RE.match(text)
            if not m:
                # 既知 prefix と一致しない anchor は対象外(目次リンク等)
                continue
            month, day, year = m.group(1), m.group(2), m.group(3)
            published = parse_jp_date(f"{year}/{int(month):02d}/{int(day):02d}")
            title = text[m.end():].strip()
            if not title or len(title) < 4:
                continue
            seen_urls.add(absolute)
            items.append({
                "url": absolute,
                "title": title,
                "published": published,
                "author": None,
                "summary": "",
            })
        return items
