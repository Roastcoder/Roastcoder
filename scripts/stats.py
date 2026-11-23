#!/usr/bin/env python3
"""Draws the profile stats cards (assets/stats.svg, top-languages.svg, heatmap.svg) from the GitHub API.

Runs daily in .github/workflows/stats.yml. Uses the `gh` CLI, so it needs GH_TOKEN (or a local `gh auth login`).
Self-check: python3 scripts/stats.py --test
"""
import json, os, subprocess, sys
from datetime import date, timedelta
from html import escape
from pathlib import Path

LOGIN = "Roastcoder"
OUT = Path(__file__).resolve().parent.parent / "assets"
BG, PANEL, LINE, LIME, TEXT, MUTED = "#0D1117", "#11161C", "#232A31", "#B9FF66", "#F7F8F3", "#8B949E"
FONT = "font-family=\"'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif\""
MONO = "font-family=\"'Fira Code',ui-monospace,SFMono-Regular,Menlo,monospace\""

QUERY = """query($login:String!){user(login:$login){
  createdAt followers{totalCount}
  repositories(ownerAffiliations:OWNER,isFork:false,first:100,privacy:PUBLIC,orderBy:{field:PUSHED_AT,direction:DESC}){
    totalCount nodes{stargazerCount languages(first:8,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}
  contributionsCollection{totalCommitContributions restrictedContributionsCount totalPullRequestContributions totalIssueContributions
    contributionCalendar{totalContributions weeks{contributionDays{contributionCount date}}}}}}"""


LANG_QUERY = """query($endCursor:String){viewer{login repositories(ownerAffiliations:OWNER,isFork:false,first:100,after:$endCursor){
  pageInfo{hasNextPage endCursor} nodes{languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}}}"""
MARKUP = {"HTML", "CSS", "SCSS", "Less", "Jupyter Notebook"}


def fetch():
    raw = subprocess.check_output(["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"login={LOGIN}"])
    return json.loads(raw)["data"]["user"]


def fetch_all_repos():
    """All own repos, private included. Needs a token that belongs to the account (local gh login or STATS_TOKEN)."""
    env = dict(os.environ, GH_TOKEN=os.environ["STATS_TOKEN"]) if os.environ.get("STATS_TOKEN") else None
    try:
        raw = subprocess.check_output(["gh", "api", "graphql", "--paginate", "--slurp", "-f", f"query={LANG_QUERY}"], env=env)
    except subprocess.CalledProcessError:  # the plain Actions token has no viewer
        return None
    pages = json.loads(raw)
    if pages[0]["data"]["viewer"]["login"].lower() != LOGIN.lower():
        return None
    return [r for p in pages for r in p["data"]["viewer"]["repositories"]["nodes"]]


def streaks(days):
    """Current and longest run of days with at least one contribution. Today may still be empty."""
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    current = 0
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"]:
            current += 1
        elif i:  # an empty today does not break the streak yet
            break
    return current, longest


def languages(repos, top=6):
    """Each repo counts once, split by its code size, so one huge repo cannot outweigh the rest. Markup is left out."""
    sizes = {}
    for r in repos:
        edges = [e for e in r["languages"]["edges"] if e["node"]["name"] not in MARKUP]
        repo_total = sum(e["size"] for e in edges)
        for e in edges:
            name, color = e["node"]["name"], e["node"]["color"] or MUTED
            sizes.setdefault(name, [0, color])[0] += e["size"] / repo_total
    total = sum(s for s, _ in sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1][0])[:top]
    return [(n, c, s / total * 100) for n, (s, c) in ranked]


def card(width, height, body, title):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<rect width="{width}" height="{height}" rx="16" fill="{BG}" stroke="{LINE}"/>
<circle cx="26" cy="26" r="5" fill="#FF5F56"/><circle cx="44" cy="26" r="5" fill="#FFBD2E"/><circle cx="62" cy="26" r="5" fill="{LIME}"/>
<text x="84" y="31" fill="{MUTED}" font-size="13" {MONO}>{escape(title)}</text>
{body}
</svg>"""


def stats_svg(u, current, longest, updated):
    c = u["contributionsCollection"]
    tiles = [
        (f"{c['contributionCalendar']['totalContributions']:,}", "contributions this year"),
        (f"{c['totalCommitContributions']:,}", "public commits"),
        (f"{current}", "day streak 🔥"),
        (f"{longest}", "longest streak"),
        (f"{u['repositories']['totalCount']}", "public repos"),
        (f"{c['restrictedContributionsCount']:,}", "private contributions"),
    ]
    body = []
    for i, (value, label) in enumerate(tiles):
        x, y = 24 + (i % 3) * 252, 56 + (i // 3) * 104
        body.append(f'<rect x="{x}" y="{y}" width="236" height="88" rx="12" fill="{PANEL}" stroke="{LINE}"/>'
                    f'<text x="{x + 18}" y="{y + 46}" fill="{LIME if i < 3 else TEXT}" font-size="32" font-weight="700" {FONT}>{escape(value)}</text>'
                    f'<text x="{x + 18}" y="{y + 72}" fill="{MUTED}" font-size="14" {FONT}>{escape(label)}</text>')
    body.append(f'<text x="780" y="286" text-anchor="end" fill="{MUTED}" font-size="11" {MONO}>updated {updated}</text>')
    return card(804, 300, "\n".join(body), "~/stats --year")


def languages_svg(langs):
    bar, x = [], 24.0
    for name, color, pct in langs:
        w = 756 * pct / 100
        bar.append(f'<rect x="{x:.1f}" y="58" width="{max(w, 2):.1f}" height="12" fill="{color}"/>')
        x += w
    rows = []
    for i, (name, color, pct) in enumerate(langs):
        cx, cy = 24 + (i % 3) * 252, 104 + (i // 3) * 34
        rows.append(f'<circle cx="{cx + 7}" cy="{cy - 5}" r="7" fill="{color}"/>'
                    f'<text x="{cx + 22}" y="{cy}" fill="{TEXT}" font-size="15" {FONT}>{escape(name)}</text>'
                    f'<text x="{cx + 228}" y="{cy}" text-anchor="end" fill="{MUTED}" font-size="14" {MONO}>{pct:.1f}%</text>')
    clip = '<clipPath id="r"><rect x="24" y="58" width="756" height="12" rx="6"/></clipPath>'
    return card(804, 186, f'<defs>{clip}</defs><g clip-path="url(#r)">{"".join(bar)}</g>' + "\n".join(rows), "~/languages --top")


def heatmap_svg(weeks):
    levels = ["#161B22", "#2B4A12", "#4E8A1C", "#86CC3A", LIME]
    peak = max((d["contributionCount"] for w in weeks for d in w["contributionDays"]), default=0) or 1
    cells = []
    for wi, w in enumerate(weeks[-53:]):
        for d in w["contributionDays"]:
            day = date.fromisoformat(d["date"]).isoweekday() % 7
            n = d["contributionCount"]
            lvl = 0 if n == 0 else min(4, 1 + int(3 * (n / peak) ** 0.5 + 0.5))  # sqrt so one busy day does not dim the rest
            cells.append(f'<rect x="{24 + wi * 14.4:.1f}" y="{56 + day * 14.4:.1f}" width="11.5" height="11.5" rx="2.5" fill="{levels[lvl]}"><title>{n} on {d["date"]}</title></rect>')
    legend = "".join(f'<rect x="{676 + i * 16}" y="172" width="11.5" height="11.5" rx="2.5" fill="{c}"/>' for i, c in enumerate(levels))
    legend += f'<text x="668" y="182" text-anchor="end" fill="{MUTED}" font-size="11" {MONO}>less</text><text x="760" y="182" fill="{MUTED}" font-size="11" {MONO}>more</text>'
    return card(804, 198, "".join(cells) + legend, "~/activity --last-year")


def render(u):
    days = [d for w in u["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    OUT.mkdir(exist_ok=True)
    (OUT / "stats.svg").write_text(stats_svg(u, current, longest, date.today().isoformat()))
    repos = fetch_all_repos()
    if repos:  # without a token for the account (plain Actions token), keep the last languages card
        (OUT / "top-languages.svg").write_text(languages_svg(languages(repos)))
    (OUT / "heatmap.svg").write_text(heatmap_svg(u["contributionsCollection"]["contributionCalendar"]["weeks"]))


def self_test():
    day = lambda n, i: {"contributionCount": n, "date": (date(2026, 1, 1) + timedelta(i)).isoformat()}
    assert streaks([day(1, 0), day(1, 1), day(0, 2), day(1, 3), day(1, 4), day(1, 5)]) == (3, 3)
    assert streaks([day(1, 0), day(1, 1), day(0, 2)]) == (2, 2)  # empty today keeps yesterday's streak
    assert streaks([day(1, 0), day(0, 1), day(0, 2)]) == (0, 1)
    repo = lambda *e: {"languages": {"edges": [{"size": s, "node": {"name": n, "color": None}} for n, s in e]}}
    langs = languages([repo(("PHP", 75), ("JS", 25), ("HTML", 900)), repo(("JS", 100)), repo(("HTML", 50))])
    assert [n for n, _, _ in langs] == ["JS", "PHP"] and langs[0][2] == 62.5  # per repo, HTML ignored
    print("ok")


if __name__ == "__main__":
    self_test() if "--test" in sys.argv else render(fetch())
