import html
import json
import re
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from core.models import Entry, Feed


REPO = "BuilderPulse/BuilderPulse"
BRANCH = "main"
ZH_ATOM_URL = f"https://github.com/{REPO}/commits/{BRANCH}/zh.atom"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"


@dataclass
class BuilderPulseReport:
    report_date: str
    title: str
    blob_url: str
    raw_url: str
    commit_url: str
    commit_updated_at: str
    markdown: str
    html: str
    summary: str


def http_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    data: bytes | None = None,
) -> bytes:
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_text(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    data: bytes | None = None,
) -> str:
    return http_request(url, method=method, headers=headers, data=data).decode("utf-8")


def parse_latest_report_dates(atom_xml: str, limit: int) -> list[tuple[str, str, str]]:
    root = ET.fromstring(atom_xml)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    pattern = re.compile(r"Daily:\s*(\d{4}-\d{2}-\d{2})")

    candidates: list[tuple[str, str, str]] = []
    seen_dates: set[str] = set()

    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        match = pattern.search(title)
        if not match:
            continue
        date_str = match.group(1)
        if date_str in seen_dates:
            continue
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        link = entry.find("a:link", ns)
        href = link.attrib.get("href", "") if link is not None else ""
        candidates.append((date_str, updated, href))
        seen_dates.add(date_str)
        if len(candidates) >= limit:
            break

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[:limit]


def build_paths(report_date: str) -> tuple[str, str]:
    year = report_date[:4]
    rel = f"zh/{year}/{report_date}.md"
    blob = f"https://github.com/{REPO}/blob/{BRANCH}/{rel}"
    raw = f"{RAW_BASE}/{rel}"
    return blob, raw


def extract_title(markdown: str, fallback_date: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return f"BuilderPulse Daily — {fallback_date}"


def extract_summary(markdown: str) -> str:
    lines = [line.strip() for line in markdown.splitlines()]
    clean: list[str] = []

    for line in lines:
        if not line or line.startswith("#") or line == "---" or line.startswith("![]("):
            continue
        clean.append(line.lstrip("> ").strip() if line.startswith(">") else line)
        if len(" ".join(clean)) >= 280:
            break

    summary = " ".join(clean)
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > 320:
        summary = summary[:317].rstrip() + "..."
    return summary


def render_html_with_github(markdown: str) -> str:
    payload = json.dumps(
        {
            "text": markdown,
            "mode": "gfm",
            "context": REPO,
        }
    ).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "builderpulse-rsshub",
    }
    return fetch_text(
        "https://api.github.com/markdown",
        method="POST",
        headers=headers,
        data=payload,
    )


def render_html_fallback(markdown: str) -> str:
    parts: list[str] = []
    in_code_block = False
    code_lines: list[str] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = " ".join(line.strip() for line in paragraph_lines if line.strip())
        if text:
            parts.append(f"<p>{html.escape(text)}</p>")
        paragraph_lines = []

    def flush_code_block() -> None:
        nonlocal code_lines
        parts.append(f"<pre><code>{html.escape(''.join(code_lines))}</code></pre>")
        code_lines = []

    for raw_line in markdown.splitlines(keepends=True):
        stripped = raw_line.rstrip("\n")
        if stripped.startswith("```"):
            flush_paragraph()
            if in_code_block:
                flush_code_block()
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(raw_line)
            continue

        line = stripped.strip()
        if not line:
            flush_paragraph()
            continue

        if line.startswith("# "):
            flush_paragraph()
            parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
            continue
        if line.startswith("### "):
            flush_paragraph()
            parts.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()
    if in_code_block:
        flush_code_block()

    return "".join(parts)


def render_html(markdown: str) -> str:
    try:
        return render_html_with_github(markdown)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return render_html_fallback(markdown)


def wrap_html(report: BuilderPulseReport) -> str:
    meta = textwrap.dedent(
        f"""
        <div style="font-family: ui-sans-serif, system-ui, sans-serif; color: #475569; font-size: 14px; margin-bottom: 24px;">
          <p><strong>Source</strong>: BuilderPulse Chinese Daily</p>
          <p><strong>Report Date</strong>: {report.report_date}</p>
          <p><strong>Latest Upstream Commit</strong>: {report.commit_updated_at}</p>
          <p>
            <a href="{report.blob_url}">GitHub Article</a>
            &nbsp;|&nbsp;
            <a href="{report.raw_url}">Raw Markdown</a>
            &nbsp;|&nbsp;
            <a href="{report.commit_url}">Latest Commit</a>
          </p>
        </div>
        """
    ).strip()
    return f"<article>{meta}{report.html}</article>"


def discover_reports(limit: int) -> list[BuilderPulseReport]:
    reports: list[BuilderPulseReport] = []
    for date_str, updated, commit_url in parse_latest_report_dates(fetch_text(ZH_ATOM_URL), limit):
        blob_url, raw_url = build_paths(date_str)
        markdown = fetch_text(raw_url)
        reports.append(
            BuilderPulseReport(
                report_date=date_str,
                title=extract_title(markdown, date_str),
                blob_url=blob_url,
                raw_url=raw_url,
                commit_url=commit_url,
                commit_updated_at=updated,
                markdown=markdown,
                html=wrap_html(
                    BuilderPulseReport(
                        report_date=date_str,
                        title=extract_title(markdown, date_str),
                        blob_url=blob_url,
                        raw_url=raw_url,
                        commit_url=commit_url,
                        commit_updated_at=updated,
                        markdown=markdown,
                        html=render_html(markdown),
                        summary=extract_summary(markdown),
                    )
                ),
                summary=extract_summary(markdown),
            )
        )
    return reports


def parse_datetime_or_none(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_builderpulse_feed(feed: Feed):
    reports = discover_reports(feed.max_posts)
    if not reports:
        raise RuntimeError("No BuilderPulse reports discovered")

    latest_report = reports[0]
    if not feed.name or feed.name in {"Loading", "Empty"}:
        feed.name = "BuilderPulse Chinese Daily"
    feed.subtitle = "BuilderPulse Chinese daily report mirror"
    feed.author = "BuilderPulse"
    feed.language = "zh-cn"
    feed.link = "https://github.com/BuilderPulse/BuilderPulse"
    feed.pubdate = parse_datetime_or_none(latest_report.commit_updated_at)
    feed.updated = parse_datetime_or_none(latest_report.commit_updated_at)
    feed.last_fetch = timezone.now()
    feed.fetch_status = True
    feed.log = f"{timezone.now()} BuilderPulse fetch completed <br>"
    feed.save()

    for report in reports:
        Entry.objects.update_or_create(
            feed=feed,
            guid=report.report_date,
            defaults={
                "link": report.blob_url,
                "author": "BuilderPulse",
                "pubdate": parse_datetime_or_none(report.commit_updated_at),
                "updated": parse_datetime_or_none(report.commit_updated_at),
                "original_title": report.title,
                "original_content": report.html,
                "original_summary": report.summary,
            },
        )
