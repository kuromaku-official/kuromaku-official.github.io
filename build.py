"""
KUROMAKU イベントカレンダーのページを作るスクリプト

- いつものカレンダー(kuromaku.contact@gmail.com)からは「◯◯集団コンサル」だけを拾う
- 「KUROMAKUイベント（公開用）」カレンダーからは、入っている予定をすべて拾う
  （タイトルに「オフ会」が入っていればオフ会、それ以外は勉強会として表示）

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
    # 場所はURL(Zoomなど)が入っていない時だけ出す
    place = e.get("location", "")
    if place and not re.search(r"https?://|zoom", place, re.I):
        item["place"] = html.escape(place)
    return item


def main():
    creds = Credentials.from_service_account_file(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service-account.json"),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    creds.refresh(google.auth.transport.requests.Request())

    today = datetime.datetime.now(JST).date()
    time_min = f"{today.replace(day=1) - datetime.timedelta(days=31):%Y-%m-01}T00:00:00+09:00"
    time_max = f"{today + datetime.timedelta(days=200):%Y-%m-%d}T23:59:59+09:00"

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
    items.sort(key=lambda i: i["start"])

    data = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    page = (HERE / "template.html").read_text(encoding="utf-8")
    page = page.replace("/*EVENTS*/[]", data).replace("/*BUILT_AT*/", f"{datetime.datetime.now(JST):%-m/%-d %H:%M}")
    out = HERE / "_site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(items)}件の予定でページを作りました")


if __name__ == "__main__":
    main()
