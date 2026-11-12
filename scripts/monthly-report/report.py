#!/usr/bin/env python3
"""
月度提交月报：统计 GitHub 仓库上个月的提交，把「一次都没提交」的人推到钉钉群。

只依赖 Python 标准库 + git 命令。

用法：
    python3 report.py --config config.json --members members.local.json   # 本地调试并推送
    python3 report.py --config config.json --members members.local.json --dry-run   # 只打印不发送
    python3 report.py --config config.json --members members.local.json --month 2026-10
    python3 report.py --config config.json --members members.local.json --export-members

成员名单来源优先级（仓库是公开的，手机号不能进 git 历史）：
    --members 文件  >  MEMBERS_JSON 环境变量  >  config.json 里的 members
    GitHub Actions 上名单放在仓库 Secret MEMBERS_JSON 里，仓库里只留仓库配置。

环境变量：
    DINGTALK_WEBHOOK   钉钉机器人 Webhook 完整地址
    DINGTALK_SECRET    钉钉机器人加签密钥（安全设置选「加签」时必填）
    MEMBERS_JSON       成员名单 JSON（线上用，内容同 members.local.json）
    GH_TOKEN           读私有仓库用的 GitHub Token（public 仓库可留空）
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- 时间区间


def month_range(tz_hours: int, month: str | None = None) -> tuple[datetime, datetime]:
    """返回 [上个月 1 号 00:00, 本月 1 号 00:00) 的带时区时间。"""
    tz = timezone(timedelta(hours=tz_hours))
    now = datetime.now(tz)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=tz)
        end = (start + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, end
    start = (this_month_start - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, this_month_start


# ---------------------------------------------------------------- 拉代码


def run_git(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True, errors="replace"
    ).stdout


def prepare_repo(cfg: dict, tmpdir: str) -> Path:
    """repo_url 为 "self" 时直接用当前工作目录，否则镜像克隆一份到临时目录。"""
    spec = (cfg.get("repo_url") or "self").strip()
    if spec in ("self", ".", ""):
        log("使用当前工作目录作为仓库")
        return Path.cwd()

    token = os.environ.get(cfg.get("github_token_env", "GH_TOKEN"), "").strip()
    url = spec
    if token and url.startswith("https://"):
        url = "https://x-access-token:" + token + "@" + url[len("https://"):]

    target = Path(tmpdir) / "repo.git"
    log(f"克隆 {spec} ...")
    base = ["git", "clone", "--mirror", "--quiet"]
    try:
        run_git(base + ["--filter=blob:none", url, str(target)])
    except subprocess.CalledProcessError:
        shutil.rmtree(target, ignore_errors=True)
        run_git(base + [url, str(target)])
    return target


def git_records(repo: Path, start: datetime, end: datetime) -> list[dict]:
    """返回窗口内的提交，每条带上改动文件及状态（A=新增 / M=修改 / D=删除）。

    篇数只认新增（A），所以必须用 --name-status 而不是 --name-only：
    大量补充翻译、改格式的提交会碰到很多老论文目录，那些不该算成「新提交了几篇」。
    """
    since = (start - timedelta(days=90)).isoformat()
    out = run_git([
        "git", "-C", str(repo), "log", "--all", "--no-merges",
        f"--since={since}", "--name-status",
        "--pretty=format:@@C@@%ae\x09%an\x09%aI\x09%s",
    ])

    records: list[dict] = []
    cur: dict | None = None
    for line in out.splitlines():
        if line.startswith("@@C@@"):
            if cur:
                records.append(cur)
            parts = line[len("@@C@@"):].split("\t")
            cur = None
            if len(parts) < 4:
                continue
            email, name, iso = parts[0], parts[1], parts[2]
            subject = "\t".join(parts[3:])
            try:
                dt = datetime.fromisoformat(iso)
            except ValueError:
                continue
            cur = {
                "email": email.strip().lower(),
                "name": name.strip(),
                "date": dt,
                "subject": subject.strip(),
                "files": [],
            }
        elif cur is not None and line.strip():
            parts = line.split("\t")
            if len(parts) >= 2:
                cur["files"].append((parts[0], parts[-1]))

    if cur:
        records.append(cur)

    return [r for r in records if start <= r["date"] < end]


# ---------------------------------------------------------------- 统计


def git_subjects(repo: Path, until: datetime) -> list[tuple[str, str, str]]:
    """取 until 之前的全部提交的 (email, name, subject)，用于统计历史累计篇数。

    只看提交信息，不带文件列表，比 git_records 轻得多；补跑历史月份时
    until 传当月窗口的右边界，累计值就是「截至那个月末」的数字。
    """
    out = run_git([
        "git", "-C", str(repo), "log", "--all", "--no-merges",
        f"--until={until.isoformat()}",
        "--pretty=format:%ae\x09%an\x09%s",
    ])
    rows: list[tuple[str, str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append((parts[0].strip().lower(), parts[1].strip(), "\t".join(parts[2:])))
    return rows


def gh_list(member: dict) -> list[str]:
    """github 字段兼容两种写法："user" 或 ["user1", "user2"]。"""
    g = member.get("github") or []
    return [g] if isinstance(g, str) else g


def match_member(email: str, member: dict) -> bool:
    if email in {e.lower() for e in member.get("emails", [])}:
        return True
    for gh in gh_list(member):
        gh = gh.lower()
        if email == f"{gh}@users.noreply.github.com":
            return True
        if email.endswith(f"+{gh}@users.noreply.github.com"):
            return True
    return False


def aggregate(members, records, ignore_patterns, paper_pattern):
    patterns = [re.compile(p, re.I) for p in ignore_patterns]
    paper_re = re.compile(paper_pattern, re.I)

    def ignored(email: str, name: str) -> bool:
        return any(p.search(email) or p.search(name) for p in patterns)

    counts: dict[str, int] = {}
    papers: dict[str, set[str]] = {}
    names: dict[str, str] = {}

    for r in records:
        email = r["email"]
        if ignored(email, r["name"]):
            continue
        counts[email] = counts.get(email, 0) + 1
        # 篇数按 commit 信息里的「add paper card for <论文名>」统计，同名论文多次改只算一篇。
        # 不按文件路径统计：重构目录、批量补充翻译会产生大量 A/M 文件，会把篇数算飞。
        hit = paper_re.search(r["subject"])
        if hit:
            title = r["subject"][hit.end():].strip().lower() or r["subject"].lower()
            papers.setdefault(email, set()).add(title)
        else:
            papers.setdefault(email, set())
        names.setdefault(email, r["name"])

    stats: dict[str, dict] = {}
    unmatched: dict[str, int] = {}
    matched: set[str] = set()

    for m in members:
        hits = [e for e in counts if match_member(e, m)]
        matched.update(hits)
        stats[m["name"]] = {
            "commits": sum(counts[e] for e in hits),
            "papers": len(set().union(*[papers.get(e, set()) for e in hits])) if hits else 0,
        }

    for email, n in counts.items():
        if email not in matched:
            unmatched[email] = n

    return stats, unmatched, names


def cumulative_papers(members, subjects, ignore_patterns, paper_pattern) -> dict[str, int]:
    """每个成员截至统计月末的历史累计篇数（同名论文只算一次）。"""
    patterns = [re.compile(p, re.I) for p in ignore_patterns]
    paper_re = re.compile(paper_pattern, re.I)

    by_email: dict[str, set[str]] = {}
    for email, name, subject in subjects:
        if any(p.search(email) or p.search(name) for p in patterns):
            continue
        hit = paper_re.search(subject)
        if not hit:
            continue
        title = subject[hit.end():].strip().lower() or subject.lower()
        by_email.setdefault(email, set()).add(title)

    result: dict[str, int] = {}
    for m in members:
        titles: set[str] = set()
        for email, names in by_email.items():
            if match_member(email, m):
                titles |= names
        result[m["name"]] = len(titles)
    return result


# ---------------------------------------------------------------- 消息


def render(cfg, start, end, stats, unmatched, names, tz_hours, cumulative=None) -> str:
    """按 msgtype 生成消息正文。

    text（默认）：纯文本，@手机号 会被客户端渲染成蓝色昵称，两端都可点击、能高亮。
    markdown：有标题和加粗，但官方明确「Markdown 类型 @ 人员不支持高亮」，
              手机上只会显示成 @手机号 原文，不渲染成昵称。
    两种类型正文里的 @ 都必须写手机号——钉钉只认这个，写 @姓名 连通知都不会触发。
    """
    cumulative = cumulative or {}
    show_cum = cfg.get("show_cumulative_papers", True)
    display = cfg.get("repo_display_name") or "仓库"
    plain = cfg.get("msgtype", "text") != "markdown"

    people = list(stats.items())
    missing = [n for n, s in people if s["commits"] == 0]
    active = sorted(
        [(n, s) for n, s in people if s["commits"] > 0],
        key=lambda x: (-x[1]["papers"], -x[1]["commits"]),
    )
    total_commits = sum(s["commits"] for _, s in people) + sum(unmatched.values())

    mobile_of = {m["name"]: (m.get("mobile") or "").strip() for m in cfg["members"]}
    tag = cfg.get("title_prefix", "").strip()

    def b(s: str) -> str:
        """加粗；纯文本模式原样返回。"""
        return s if plain else f"**{s}**"

    def line(s: str) -> str:
        """列表项；纯文本模式去掉 markdown 的短横线。"""
        return s if plain else f"- {s}"

    def at(name: str) -> str:
        mob = mobile_of.get(name, "")
        return f"@{mob}" if mob else f"@{name}"

    title = f"{tag + ' ' if tag else ''}{display} · {start.year} 年 {start.month} 月提交月报"
    blocks: list[str] = [title if plain else f"### {title}"]

    blocks.append("\n".join([
        f"{b('统计区间')}：{start:%Y-%m-%d} ~ {end - timedelta(days=1):%Y-%m-%d}",
        f"{b('参与统计')}：{len(people)} 人 ｜ {b('提交总数')}：{total_commits} 次",
        f"{b('覆盖范围')}：全部分支，已排除合并提交与机器人",
    ]))

    if unmatched:
        blocks.append(
            f"{b('统计口径提示')}：有 {len(unmatched)} 个邮箱没能匹配到任何成员，"
            f"对应提交未计入个人名下，下面的名单可能因此失真，请把邮箱补进成员名单"
        )

    miss = [b(f"上月未提交（{len(missing)} 人）")]
    miss += [line(at(n)) for n in missing] if missing else [line("无，全员都有提交")]
    blocks.append("\n".join(miss))

    if cfg.get("also_report_submitters", True) and active:
        rows = [b(f"已提交（{len(active)} 人）")]
        for name, s in active:
            tail = f" ｜ 累计 {cumulative.get(name, 0)} 篇" if show_cum else ""
            rows.append(line(f"{name}：{s['papers']} 篇 / {s['commits']} 次{tail}"))
        total_p = sum(s["papers"] for _, s in active)
        total_c = sum(s["commits"] for _, s in active)
        tail = f" ｜ 累计 {sum(cumulative.get(n, 0) for n, _ in active)} 篇" if show_cum else ""
        rows.append(line(b(f"合计：{total_p} 篇 / {total_c} 次{tail}")))
        blocks.append("\n".join(rows))

    if unmatched:
        known = {m["name"] for m in cfg["members"]}
        rows = [b(f"未匹配到成员名单的邮箱（{len(unmatched)} 个）")]
        for email, n in sorted(unmatched.items(), key=lambda x: -x[1]):
            who = names.get(email, "")
            if who and who in known:
                note = f"（{who}，同名成员，建议加入其 emails）"
            elif who:
                note = f"（{who}）"
            else:
                note = ""
            rows.append(line(f"{email}{note}：{n} 次"))
        blocks.append("\n".join(rows))

    footer = cfg.get("message_footer", "").strip()
    if footer:
        blocks.append(footer if plain else f"> {footer}")

    return "\n\n".join(blocks)


def send_dingtalk(webhook: str, secret: str, title: str, text: str,
                  at_mobiles: list[str], msgtype: str = "text") -> dict:
    url = webhook
    if secret:
        ts = str(round(time.time() * 1000))
        to_sign = f"{ts}\n{secret}"
        digest = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={sign}"

    at_obj = {"atMobiles": [m for m in at_mobiles if m], "isAtAll": False}
    if msgtype == "markdown":
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
            "at": at_obj,
        }
    else:
        payload = {"msgtype": "text", "text": {"content": text}, "at": at_obj}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("errcode") != 0:
        raise RuntimeError(f"钉钉返回错误：{body}")
    log("已推送到钉钉群")
    return body


# ---------------------------------------------------------------- 成员名单


def load_members(cfg: dict, members_file: str | None) -> list[dict]:
    """成员名单来源优先级：--members 文件 > MEMBERS_JSON 环境变量 > config 内的 members。

    线上跑 GitHub Actions 时名单放在仓库 Secret 里（仓库是公开的，
    手机号不能进 git 历史）；本地调试用 --members 指向不进版本库的本地文件。
    """
    env_name = cfg.get("members_env", "MEMBERS_JSON")

    raw: str | None = None
    source = ""
    if members_file:
        p = Path(members_file)
        if not p.exists():
            raise SystemExit(f"成员文件不存在：{members_file}")
        raw, source = p.read_text(encoding="utf-8"), members_file
    elif os.environ.get(env_name, "").strip():
        raw, source = os.environ[env_name], f"环境变量 {env_name}"

    if raw is not None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{source} 不是合法 JSON：{e}")
        members = data.get("members") if isinstance(data, dict) else data
        if not isinstance(members, list):
            raise SystemExit(f"{source} 里找不到成员数组（应为 [...] 或 {{\"members\": [...]}}）")
        log(f"成员名单：{len(members)} 人（来自 {source}）")
        return members

    members = cfg.get("members") or []
    if members:
        log(f"成员名单：{len(members)} 人（来自 {cfg.get('_path', 'config.json')}）")
    return members


def export_members(members: list[dict]) -> str:
    """输出可直接粘进 GitHub Secret 的单行 JSON。"""
    return json.dumps(members, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--members", help="成员名单文件（本地调试用，不建议提交进仓库）")
    ap.add_argument("--dry-run", action="store_true", help="只打印消息，不发送")
    ap.add_argument("--month", help="补跑指定月份，格式 YYYY-MM，默认上个月")
    ap.add_argument("--export-members", action="store_true",
                    help="打印成员名单的单行 JSON，用于粘贴到 GitHub Secret")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    cfg["_path"] = args.config
    members = load_members(cfg, args.members)
    cfg["members"] = members

    if args.export_members:
        print(export_members(members))
        return 0

    if not members:
        log("成员名单为空：请用 --members 指定文件，或设置 MEMBERS_JSON 环境变量")
        return 1

    tz_hours = cfg.get("timezone_offset_hours", 8)
    start, end = month_range(tz_hours, args.month)
    log(f"统计区间：{start:%Y-%m-%d} ~ {end - timedelta(days=1):%Y-%m-%d}")

    with tempfile.TemporaryDirectory() as tmp:
        repo = prepare_repo(cfg, tmp)
        records = git_records(repo, start, end)
        subjects = git_subjects(repo, end) if cfg.get("show_cumulative_papers", True) else []

    log(f"窗口内有效提交：{len(records)} 条")
    stats, unmatched, names = aggregate(
        cfg["members"],
        records,
        cfg.get("ignore_patterns", []),
        cfg.get("paper_commit_pattern", r"add\s+paper\s*card"),
    )
    cumulative = cumulative_papers(
        cfg["members"],
        subjects,
        cfg.get("ignore_patterns", []),
        cfg.get("paper_commit_pattern", r"add\s+paper\s*card"),
    )
    text = render(cfg, start, end, stats, unmatched, names, tz_hours, cumulative)

    if args.dry_run:
        print(text)
        return 0

    webhook = os.environ.get(cfg.get("dingtalk_webhook_env", "DINGTALK_WEBHOOK"), "").strip()
    secret = os.environ.get(cfg.get("dingtalk_secret_env", "DINGTALK_SECRET"), "").strip()
    if not webhook:
        log("缺少 DINGTALK_WEBHOOK 环境变量")
        return 1

    mobile_of = {m["name"]: (m.get("mobile") or "").strip() for m in cfg["members"]}
    missing = [n for n, s in stats.items() if s["commits"] == 0]
    title = f"{cfg.get('repo_display_name', '仓库')} {start.month} 月提交月报"
    send_dingtalk(
        webhook, secret, title, text,
        [mobile_of.get(n, "") for n in missing],
        cfg.get("msgtype", "text"),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
