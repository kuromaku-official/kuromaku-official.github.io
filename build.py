"""
KUROMAKU イベントカレンダーのページを作るスクリプト

- いつものカレンダー(kuromaku.contact@gmail.com)からは「◯◯集団コンサル」だけを拾う
- 「KUROMAKUイベント（公開用）」カレンダーからは、入っている予定をすべて拾う
  （タイトルに「オフ会」が入っていればオフ会、それ以外は勉強会として表示）
- タームは毎月20日〜翌月19日。毎月1日に次のタームを告知するので、
  ページに出すのは「来月19日まで」（1日になった時点で次のタームが出る）

使い方: python3 build.py   → _site/index.html ができる
環境変数 GOOGLE_SERVICE_ACCOUNT_JSON にサービスアカウントの鍵ファイルのパスを入れておく
"""

import datetime
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import google.auth.transport.requests
import requests
from google.oauth2.service_account import Credentials

MAIN_CAL = "kuromaku.contact@gmail.com"
EVENT_CAL = "f710c5a8ee32f4a8e84100c1f854bf6fa654348ec429504352a7a502b22b2ff3@group.calendar.google.com"
CONSUL = {"あっきー": "akky", "あんにん": "annin", "みしゃまる": "misha", "そら": "sora"}
JST = datetime.timezone(datetime.timedelta(hours=9))
# 場所欄にこれが入っていたらオンライン会議の情報とみなして載せない
PRIVATE_PLACE = re.compile(
    r"https?://|zoom|meet\.google\.com|teams\.microsoft\.com|\.com/|パスコード|passcode|ミーティングID|meeting id",
    re.I,
)
HERE = Path(__file__).parent


def fetch(token, cal_id, time_min, time_max):
    r = requests.get(
        f"https://www.googleapis.com/calendar/v3/calendars/{quote(cal_id)}/events",
        headers={"Authorization": f"Bearer {token}"},
        params={"timeMin": time_min, "timeMax": time_max, "singleEvents": "true",
                "orderBy": "startTime", "maxResults": "500"},
        timeout=20,
    )
    r.raise_for_status()
    return [e for e in r.json().get("items", []) if e.get("status") != "cancelled"]


def to_item(e, cat):
    start, end = e["start"], e["end"]
    item = {
        "title": html.escape(e.get("summary", "")),
        "cat": cat,
        "allDay": "date" in start,
        "start": start.get("dateTime", start.get("date"))[:16],
        "end": end.get("dateTime", end.get("date"))[:16],
    }
    # 場所はURLや会議のパスコードっぽいものが入っていない時だけ出す
    place = e.get("location", "")
    if place and not PRIVATE_PLACE.search(place):
        item["place"] = html.escape(place)
    return item


def visible_until(today):
    """毎月1日に次のターム(今月20日〜来月19日)を公開 → 来月19日までを出す"""
    y, m = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return datetime.date(y, m, 19)


def main():
    creds = Credentials.from_service_account_file(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service-account.json"),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    creds.refresh(google.auth.transport.requests.Request())

    today = datetime.date.fromisoformat(os.environ["TODAY"]) if os.environ.get("TODAY") else datetime.datetime.now(JST).date()
    time_min = f"{today.replace(day=1) - datetime.timedelta(days=31):%Y-%m-01}T00:00:00+09:00"
    time_max = f"{visible_until(today):%Y-%m-%d}T23:59:59+09:00"

    items = []
    for e in fetch(creds.token, MAIN_CAL, time_min, time_max):
        title = e.get("summary", "")
        if "集団コンサル" not in title:
            continue
        # 「あっきー・みしゃまる集団コンサル」のような合同回は担当ごとに1件ずつ出す
        for name, cat in CONSUL.items():
            if name in title.split("集団コンサル")[0]:
                items.append(to_item(e, cat))
    for e in fetch(creds.token, EVENT_CAL, time_min, time_max):
        items.append(to_item(e, "offkai" if "オフ会" in e.get("summary", "") else "study"))
    until = visible_until(today)
    items = [i for i in items if i["start"][:10] <= until.isoformat()]
    items.sort(key=lambda i: i["start"])

    data = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    page = (HERE / "template.html").read_text(encoding="utf-8")
    page = page.replace("/*EVENTS*/[]", data).replace("/*BUILT_AT*/", f"{datetime.datetime.now(JST):%-m/%-d %H:%M}")
    page = page.replace("/*VISIBLE_UNTIL*/", until.isoformat())
    page = page.replace("/*TODAY*/", os.environ.get("TODAY", ""))
    out = HERE / "_site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)}件の予定でページを作りました")


if __name__ == "__main__":
    main()
