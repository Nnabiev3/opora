"""Быстрая проверка страницы-портфолио без браузера (только стандартная библиотека).

Запуск из папки проекта:
    python tools/check.py            # проверяет index.html рядом
    python tools/check.py путь/к/index.html

Код выхода 1, если найдена хотя бы одна ошибка.
"""

import json
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path

EXPECTED_PRICES = {3000, 5000, 10000}  # утверждено автором: бот, лендинг, магазин
PRICE_RE = re.compile(r"(\d{1,2})[\s ]?(\d{3})[\s ]?₽")


class Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids, self.refs, self.headings = [], [], []
        self.imgs_without_alt, self.bad_blank = [], []
        self.jsonld, self._in_jsonld = [], False
        self._heading = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        for key in ("src", "href"):
            if key in a:
                self.refs.append((tag, a[key]))
        if tag == "img" and "alt" not in a:
            self.imgs_without_alt.append(a.get("src", "?"))
        if tag == "a" and a.get("target") == "_blank" and "noopener" not in (a.get("rel") or ""):
            self.bad_blank.append(a.get("href", "?"))
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = int(tag[1])
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True

    def handle_endtag(self, tag):
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = None
        if tag == "script":
            self._in_jsonld = False

    def handle_data(self, data):
        if self._heading is not None:
            self.headings.append(self._heading)
            self._heading = None
        if self._in_jsonld:
            self.jsonld.append(data)


def jpeg_size(path: Path):
    data = path.read_bytes()
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[i + 5 : i + 9])
            return width, height
        i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]
    return None


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "index.html"
    html = root.read_text(encoding="utf-8")
    base = root.parent
    page = Page()
    page.feed(html)
    errors, notes = [], []

    prices = {int(a + b) for a, b in PRICE_RE.findall(html)}
    stray = prices - EXPECTED_PRICES
    if stray:
        errors.append(f"Неутверждённые цены на странице: {sorted(stray)}")
    missing = EXPECTED_PRICES - prices
    if missing:
        errors.append(f"Не нашёл утверждённых цен: {sorted(missing)}")

    dups = sorted({i for i in page.ids if page.ids.count(i) > 1})
    if dups:
        errors.append(f"Повторяющиеся id: {dups}")

    for tag, ref in page.refs:
        if ref.startswith(("http", "#", "mailto:", "tel:", "data:", "javascript:")):
            continue
        if not (base / ref.split("?")[0]).exists():
            errors.append(f"Нет файла для <{tag}>: {ref}")

    if page.imgs_without_alt:
        errors.append(f"Картинки без alt: {page.imgs_without_alt}")
    if page.bad_blank:
        errors.append(f"target=_blank без rel=noopener: {page.bad_blank}")

    if page.headings.count(1) != 1:
        errors.append(f"h1 должен быть один, найдено {page.headings.count(1)}")
    for prev, cur in zip(page.headings, page.headings[1:]):
        if cur - prev > 1:
            errors.append(f"Пропуск уровня заголовков: h{prev} -> h{cur}")

    for block in page.jsonld:
        try:
            json.loads(block)
        except ValueError as exc:
            errors.append(f"JSON-LD не читается: {exc}")

    for marker in ('href="https://max.ru/"', "YOURDOMAIN", "TODO"):
        if marker in html:
            errors.append(f"Осталась заглушка: {marker}")

    contacts = {"telegram": html.count("t.me/mo_on_rise"), "max": html.count("max.ru/u/")}
    notes.append(f"Ссылки на контакты (шапка, первый экран, липкая кнопка, подвал): {contacts}")
    if contacts["telegram"] < 4 or contacts["max"] < 4:
        errors.append(f"Набор контактов неодинаков по блокам: {contacts}")

    og = base / "img" / "og.jpg"
    if og.exists():
        size = jpeg_size(og)
        if size != (1200, 630):
            errors.append(f"og.jpg должен быть 1200x630, сейчас {size}")
    else:
        errors.append("Нет img/og.jpg")

    print(f"Файл: {root}")
    print(f"Цены на странице: {sorted(prices)}")
    for line in notes:
        print(line)
    if errors:
        print(f"\nОШИБКИ ({len(errors)}):")
        for line in errors:
            print(" -", line)
        return 1
    print("\nВсё в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
