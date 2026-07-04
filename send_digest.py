"""
Takes a digest_input.json (produced by the daily Claude scheduled task) and:
  1. Emails it via Gmail API
  2. Appends a row to the Google Sheet
  3. Writes a markdown file into digests/
  4. Updates docs/data.json (used by the GitHub Pages site)
  5. Commits and pushes everything to GitHub

Usage: python send_digest.py
Expects digest_input.json in the same directory, shaped like:
{
  "date": "2026-07-04",
  "articles": [
    {"title": "...", "url": "...", "hn_url": "...", "summary": "...", "reason": "..."},
    {"title": "...", "url": "...", "hn_url": "...", "summary": "...", "reason": "..."},
    {"title": "...", "url": "...", "hn_url": "...", "summary": "...", "reason": "..."}
  ]
}
"""
import base64
import json
import subprocess
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/spreadsheets",
]

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"
INPUT_PATH = BASE_DIR / "digest_input.json"
DIGESTS_DIR = BASE_DIR / "digests"
DATA_JSON_PATH = BASE_DIR / "docs" / "data.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_digest():
    return json.loads(INPUT_PATH.read_text(encoding="utf-8"))


def get_google_creds():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


PAGES_URL = "https://mini03051111.github.io/ai-daily-digest/"


def build_email_body(digest):
    lines = [f"🤖 今日 AI 新聞摘要 - {digest['date']}\n"]
    for i, a in enumerate(digest["articles"], 1):
        lines.append(f"{i}. {a['title']}")
        lines.append(f"   {a['summary']}")
        lines.append(f"   💡 為什麼值得看:{a['reason']}")
        lines.append(f"   連結:{a['url']}\n")
    lines.append(f"🌐 網頁版(含歷史摘要):{PAGES_URL}")
    return "\n".join(lines)


def send_email(creds, config, digest):
    service = build("gmail", "v1", credentials=creds)
    body_text = build_email_body(digest)
    message = MIMEText(body_text)
    message["to"] = config["recipient_email"]
    message["subject"] = f"🤖 今日 AI 新聞摘要 - {digest['date']}"
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print("Email sent.")


def append_to_sheet(creds, config, digest):
    service = build("sheets", "v4", credentials=creds)
    row = [digest["date"]]
    for a in digest["articles"]:
        row.extend([a["title"], a["summary"], a["reason"], a["url"]])
    service.spreadsheets().values().append(
        spreadsheetId=config["sheet_id"],
        range="A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    print("Sheet updated.")


def write_markdown(digest):
    DIGESTS_DIR.mkdir(exist_ok=True)
    path = DIGESTS_DIR / f"{digest['date']}.md"
    lines = [f"# 🤖 今日 AI 新聞摘要 - {digest['date']}\n"]
    for i, a in enumerate(digest["articles"], 1):
        lines.append(f"## {i}. [{a['title']}]({a['url']})")
        lines.append(f"{a['summary']}\n")
        lines.append(f"💡 **為什麼值得看:** {a['reason']}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path}")


def update_pages_data(digest):
    DATA_JSON_PATH.parent.mkdir(exist_ok=True)
    entries = []
    if DATA_JSON_PATH.exists():
        entries = json.loads(DATA_JSON_PATH.read_text(encoding="utf-8"))
    entries = [e for e in entries if e["date"] != digest["date"]]
    entries.insert(0, digest)
    DATA_JSON_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print("docs/data.json updated.")


def git_publish(digest):
    subprocess.run(["git", "add", "digests", "docs"], cwd=BASE_DIR, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Daily digest {digest['date']}"],
        cwd=BASE_DIR,
        check=True,
    )
    subprocess.run(["git", "push"], cwd=BASE_DIR, check=True)
    print("Pushed to GitHub.")


def main():
    config = load_config()
    digest = load_digest()
    creds = get_google_creds()
    send_email(creds, config, digest)
    append_to_sheet(creds, config, digest)
    write_markdown(digest)
    update_pages_data(digest)
    git_publish(digest)


if __name__ == "__main__":
    main()
