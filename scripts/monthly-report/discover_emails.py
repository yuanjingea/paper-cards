#!/usr/bin/env python3
"""
扫描仓库最近的提交，把每个 GitHub 账号用过的邮箱自动补进 config.json 的 members[].emails。

为什么需要这一步：GitHub 只能通过 commit 里的邮箱把提交关联到账号。如果成员用公司邮箱
提交、又没在 GitHub 账号里绑定这个邮箱，那么仅凭 github 用户名是匹配不到的——月报会
把他误判成「未提交」。这个脚本把仓库里出现过的邮箱和账号对上，一次性配好。

用法：
    export GITHUB_TOKEN=ghp_xxx        # 强烈建议，未认证只有 60 次/小时
    python3 discover_emails.py --config config.json --repo owner/name
    python3 discover_emails.py --config config.json --repo owner/name --write

    --write  把扫到的邮箱直接写回 config.json（保留原有邮箱，合并去重）
    --days   回溯天数，默认 365
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_API = "https://api.github.com"


def api_get(base: str, path: str, token: str, params: dict | None = None) -> list:
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "commit-report"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 403 and "rate limit" in body.lower():
            raise SystemExit(
                "GitHub API 限流了（未认证只有 60 次/小时）。\n"
                "解决：export GITHUB_TOKEN=<你的 PAT> 后重跑，有 token 是 5000 次/小时。"
            )
        if e.code == 404:
            raise SystemExit(f"仓库或接口不存在：{path}（检查 --repo 拼写、以及 token 是否有读权限）")
        if e.code == 401:
            raise SystemExit("Token 无效或已过期，检查 GITHUB_TOKEN。")
        raise SystemExit(f"请求失败 {e.code}：{body[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"网络不可达：{e.reason}")


def gh_list(member: dict) -> list[str]:
    """github 字段兼容两种写法："user" 或 ["user1", "user2"]。"""
    g = member.get("github") or []
    return [g] if isinstance(g, str) else g


def parse_repo(spec: str) -> str:
    """从各种写法里抽 owner/name。"""
    s = spec.strip().rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    if "github.com" in s:
        s = s.split("github.com", 1)[1].lstrip("/:")
    parts = [p for p in s.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    raise SystemExit(f"无法从 '{spec}' 解析出 owner/name，请用 --repo owner/name 指定")


def fetch_commits(repo: str, token: str, days: int, max_pages: int, base: str) -> list:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: list = []
    for page in range(1, max_pages + 1):
        batch = api_get(
            base, f"/repos/{repo}/commits", token,
            {"per_page": 100, "page": page, "since": since},
        )
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        print(f"  第 {page} 页，累计 {len(out)} 条提交", file=sys.stderr)
        if len(batch) < 100:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--members", help="成员名单文件（默认 members.local.json，其次是 config 内的 members）")
    ap.add_argument("--repo", help="owner/name 或完整 URL，留空则从 config.repo_url 解析")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--write", action="store_true", help="把结果写回成员名单文件")
    ap.add_argument("--api-base", default=os.environ.get("GITHUB_API_BASE", DEFAULT_API))
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # 成员名单可能与 config 分离存放：优先 --members，其次 MEMBERS_JSON 环境变量
    members_path: Path | None = None
    if args.members:
        members_path = Path(args.members)
    elif Path("members.local.json").exists():
        members_path = Path("members.local.json")

    if members_path:
        raw = members_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        cfg["members"] = data.get("members") if isinstance(data, dict) else data
        target = members_path
    elif os.environ.get(cfg.get("members_env", "MEMBERS_JSON"), "").strip():
        env_name = cfg.get("members_env", "MEMBERS_JSON")
        data = json.loads(os.environ[env_name])
        cfg["members"] = data.get("members") if isinstance(data, dict) else data
        target = None
        print(f"名单来自环境变量 {env_name}，本次只预览、不写回\n", file=sys.stderr)
        args.write = False
    else:
        target = cfg_path

    repo = parse_repo(args.repo or cfg.get("repo_url", ""))
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

    if not token:
        print("提示：未设置 GITHUB_TOKEN，只能拉公开仓库且限流 60 次/小时\n", file=sys.stderr)

    print(f"扫描 {repo} 最近 {args.days} 天的提交 ...", file=sys.stderr)
    commits = fetch_commits(repo, token, args.days, args.max_pages, args.api_base)
    if not commits:
        print("没扫到提交，可能仓库为空或时间范围太短。")
        return 0

    by_login: dict[str, Counter] = defaultdict(Counter)
    display_name: dict[str, str] = {}
    orphan: Counter = Counter()

    for c in commits:
        author = c.get("commit", {}).get("author") or {}
        email = (author.get("email") or "").strip().lower()
        if not email:
            continue
        login = (c.get("author") or {}).get("login")
        if login:
            key = login.lower()
            by_login[key][email] += 1
            display_name.setdefault(key, login)
        else:
            orphan[email] += 1

    members = cfg.get("members", [])
    configured: dict[str, dict] = {}
    for m in members:
        for g in gh_list(m):
            configured[g.lower()] = m

    print(f"\n{'=' * 62}\n共 {len(commits)} 条提交，涉及 {len(by_login)} 个 GitHub 账号\n{'=' * 62}")

    print("\n【配置内的成员】")
    updated = 0
    for m in members:
        ghs = gh_list(m)
        gh_disp = " / ".join(ghs) if ghs else "未填用户名"
        print(f"\n  {m['name']} ({gh_disp})")
        if not ghs:
            print("    ! 没填 github 字段，无法自动匹配")
            continue
        emails: Counter = Counter()
        for g in ghs:
            emails.update(by_login.get(g.lower(), Counter()))
        if not emails:
            print("    - 该时间范围内没有扫到提交")
            continue
        existing = {e.lower() for e in m.get("emails", [])}
        for email, n in emails.most_common():
            mark = "（已有）" if email in existing else "（建议新增）"
            print(f"    - {email:<48} {n:>4} 次 {mark}")
        if args.write:
            merged = list(m.get("emails", []))
            have = {e.lower() for e in merged}
            for email, _ in emails.most_common():
                if email not in have:
                    merged.append(email)
                    have.add(email)
            if merged != m.get("emails", []):
                m["emails"] = merged
                updated += 1

    extra = [lg for lg in by_login if lg not in configured]
    if extra:
        print("\n【有提交、但不在成员名单里的账号】")
        for lg in sorted(extra, key=lambda x: -sum(by_login[x].values())):
            total = sum(by_login[lg].values())
            top = by_login[lg].most_common(1)[0][0]
            print(f"  {display_name.get(lg, lg):<24} {total:>4} 次   主要邮箱 {top}")
        print("  （如果是离职、外包或新同事，记得更新名单）")

    if orphan:
        print("\n【无法关联到账号的邮箱（作者没在 GitHub 绑定该邮箱）】")
        for email, n in orphan.most_common(10):
            print(f"  {email:<48} {n:>4} 次")
        print("  （这些提交只能靠手动把邮箱填进 members[].emails 才能算到人头上）")

    no_commit = [
        m["name"] for m in members
        if gh_list(m) and not any(by_login.get(g.lower()) for g in gh_list(m))
    ]
    if no_commit:
        print(f"\n【该时间范围内零提交的成员】\n  {('、'.join(no_commit))}")

    if args.write and target is not None:
        if target.name.endswith("local.json"):
            # 独立的成员名单文件：只存成员数组
            target.write_text(
                json.dumps(cfg["members"], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            target.write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(f"\n已写回 {target}（更新 {updated} 人的邮箱）")
    else:
        print("\n这是预览模式，加 --write 才会写入成员名单文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
