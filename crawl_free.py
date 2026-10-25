"""Crawl free CCAR-F / CCAR-P practice questions from public sites into data/free/<source>.json.

Usage:
    python crawl_free.py            # fetch every source
    python crawl_free.py timolabs   # fetch selected sources only

Only freely published, no-login content is fetched. After crawling, run
`python build.py` to merge everything into docs/data.js.

Normalised question shape:
    {id, cert, source, sourceUrl, domain, type: single|multi|match, question,
     options: {A: text, ...}, correctAnswer: "B" | "A,C", explanation,
     // match questions only:
     scenarios: [text], matchOptions: [text], matchAnswer: [index into matchOptions per scenario]}
"""
import html
import json
import re
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "free"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
LETTERS = "ABCDEFGHIJ"

F_DOMAINS = ["Agentic Architecture & Orchestration", "Tool Design & MCP Integration",
             "Claude Code Configuration & Workflows", "Prompt Engineering & Structured Output",
             "Context Management & Reliability"]  # official exam-guide numbering 1..5
P_DOMAINS = {
    "integration": "Integration",
    "solution": "Solution Design & Architecture",
    "evaluation": "Evaluation, Testing & Optimization",
    "governance": "Governance, Safety & Risk Management",
    "stakeholder": "Stakeholder Communication & Lifecycle Management",
    "models": "Claude Models, Prompting & Context Engineering",
    "developer": "Developer Productivity & Operational Enablement",
}


def p_domain(name: str) -> str:
    """Map any CCAR-P domain label/slug to the canonical name."""
    key = name.lower().replace("domain", "").strip(" :0123456789-")
    for k, v in P_DOMAINS.items():
        if key.startswith(k) or k in key.split("-")[0] or key.split()[0].startswith(k):
            return v
    raise ValueError(f"unknown CCAR-P domain: {name}")


def f_domain(name: str) -> str:
    key = name.lower()
    for d in F_DOMAINS:
        if d.lower().split()[0] in key.split("-")[0] or key.startswith(d.lower().split()[0]):
            return d
    raise ValueError(f"unknown CCAR-F domain: {name}")


def request(method: str, url: str, **kw) -> requests.Response:
    for attempt in range(4):
        try:
            r = requests.request(method, url, headers={**UA, **kw.pop("headers", {})}, timeout=30, **kw)
            r.raise_for_status()
            time.sleep(1)
            return r
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def get(url: str) -> str:
    return request("GET", url).text


def flight(page: str) -> str:
    """Concatenate the Next.js RSC flight payload embedded in a page."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', page)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def json_at(text: str, key: str):
    i = text.index(key) + len(key) - 1
    return json.JSONDecoder().raw_decode(text, i)[0]


def opts(seq) -> dict:
    return {LETTERS[i]: str(t).strip() for i, t in enumerate(seq)}


def q(cert, source, url, oid, domain, question, options, correct, explanation, **extra):
    correct = correct if isinstance(correct, list) else [correct]
    keys = [LETTERS[c] if isinstance(c, int) else c for c in correct]
    return {"id": f"{source}:{oid}", "cert": cert, "source": source, "sourceUrl": url, "domain": domain,
            "type": extra.pop("type", "multi" if len(keys) > 1 else "single"),
            "question": question.strip(), "options": options, "correctAnswer": ",".join(keys),
            "explanation": explanation.strip(), **extra}


# ---------------------------------------------------------------- sources

def open_exam_prep():
    out = []
    for cert, slug in [("ccar-f", "anthropic-cca-f"), ("ccar-p", "anthropic-ccar-p")]:
        url = f"https://open-exam-prep.com/practice/{slug}"
        for x in json_at(flight(get(url)), '"initialQuestions":['):
            exp = x["explanation"]
            wrong = x.get("wrongExplanations") or {}
            if wrong:
                items = wrong.items() if isinstance(wrong, dict) else enumerate(wrong)
                lines = [f"- Option {LETTERS[int(k)] if str(k).isdigit() else k}: {v}" for k, v in items if v]
                if lines:
                    exp += "\n\nWhy the other options are wrong:\n" + "\n".join(lines)
            if x.get("examTip"):
                exp += f"\n\nExam tip: {x['examTip']}"
            dom = f_domain(x["category"]) if cert == "ccar-f" else p_domain(x["category"])
            out.append(q(cert, "open-exam-prep", url, x["id"], dom, x["question"], opts(x["options"]),
                         x["correctAnswer"], exp))
    return out


def szymonpaluch():
    url = "https://szymonpaluch.com/claude-certified-architect-practice-exam"
    out = []
    for x in json_at(get(url), '"questions":['):
        stem = f"[{x['scenario']}] {x['stem']}" if x.get("scenario") else x["stem"]
        out.append(q("ccar-f", "szymonpaluch", url, x.get("id") or x["task"] + "-" + str(len(out)),
                     F_DOMAINS[int(x["domain"]) - 1], stem, opts(x["options"]), x["answer"], x["explanation"]))
    return out


def claudearchitectguide():
    """All three tracks ship as JSON.parse('...') modules in one Next.js chunk; ids f* = CCAR-F, d* = CCAR-P."""
    base = "https://claudearchitectguide.com"
    page = get(base + "/exam")
    domains = {"ccar-f": F_DOMAINS,
               "ccar-p": ["Solution Design & Architecture", "Claude Models, Prompting & Context Engineering",
                          "Integration", "Evaluation, Testing & Optimization", "Governance, Safety & Risk Management",
                          "Stakeholder Communication & Lifecycle Management",
                          "Developer Productivity & Operational Enablement"]}
    out = []
    for chunk in sorted(set(re.findall(r'/_next/static/chunks/[A-Za-z0-9_.-]+\.js', page))):
        js = get(base + chunk)
        for m in re.finditer(r"JSON\.parse\('((?:[^'\\]|\\.)*)'\)", js):
            raw = m.group(1)
            if '"ans":' not in raw:
                continue
            data = json.loads(re.sub(r"\\(['\\])", r"\1", raw))  # undo JS single-quoted string escaping
            prefix = re.match(r"[a-z]+", data[0]["id"]).group(0)
            cert = {"f": "ccar-f", "d": "ccar-p"}.get(prefix)
            if not cert:
                continue  # "dv" = CCDV-F track
            url = base + ("/" if cert == "ccar-f" else "/ccar-p")
            for x in data:
                dom = domains[cert][x["d"] - 1]
                if x.get("type") == "match":
                    out.append(q(cert, "claudearchitectguide", url, x["id"], dom, x["q"], {}, [], x["exp"],
                                 type="match", scenarios=x["scenarios"], matchOptions=x["mopts"],
                                 matchAnswer=x["ans"]))
                else:
                    out.append(q(cert, "claudearchitectguide", url, x["id"], dom, x["q"], opts(x["opts"]),
                                 x["ans"], x["exp"]))
    return out


def timolabs():
    base = "https://www.timolabs.dev/api/public-mock-exams"
    out = []
    for cert in ["ccar-f", "ccar-p"]:
        d = request("POST", base + "/attempts", json={"examId": cert, "startKey": str(uuid.uuid4())}).json()
        res = request("POST", f"{base}/attempts/{d['attempt']['id']}/submit", json={},
                      headers={"Authorization": "Bearer " + d["token"]})
        url = f"https://www.timolabs.dev/mock-exams/{cert}"
        for x in res.json()["attempt"]["result"]["review"]:
            exp = "\n".join(f"- {r['label']}: {r['text']}" for r in x.get("rationale", []))
            if x.get("evidence"):
                exp += f"\n\nReference: {x['evidence']}"
            dom = f_domain(x["domain"]) if cert == "ccar-f" else p_domain(x["domain"])
            out.append(q(cert, "timolabs", url, x["questionId"], dom, x["prompt"],
                         {o["id"]: o["text"] for o in x["options"]}, x["correctOptionIds"], exp))
    return out


def certsafari():
    out = []
    pages = [("ccar-f", "https://www.certsafari.com/anthropic/claude-certified-architect-foundations/practice-questions"),
             ("ccar-p", "https://www.certsafari.com/anthropic/claude-architect-professional/practice-questions")]
    for cert, url in pages:
        text = flight(get(url))
        # domain comes from which rendered <section "Domain N: Name"> the question text sits in
        # Each question is rendered inside a <section "Domain N: Name"> row of the RSC payload; most of its
        # articles live in other rows the section references as "$<id>". Rendered text is split across nodes
        # (inline code etc.), so match on normalised alphanumerics rather than raw strings.
        norm = lambda s: re.sub(r"[^a-z0-9]+", "", html.unescape(s).lower())
        rows = dict(re.findall(r"^([0-9a-f]+):(.*)$", text, re.M))

        def expand(body, depth=0):
            refs = re.findall(r'"\$L?([0-9a-f]+)"', body)
            return body + "".join(expand(rows[r], depth + 1) for r in refs
                                  if r in rows and depth < 3 and '["$","section","Domain' not in rows[r])

        art_text = []
        for body in rows.values():
            found = list(re.finditer(r'\["\$","section","(Domain \d+: [^"]+)"', body))
            for k, m in enumerate(found):
                seg = body[m.start():found[k + 1].start() if k + 1 < len(found) else len(body)]
                art_text.append((norm("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', expand(seg)))), m.group(1)))

        for i, x in enumerate(json_at(text, '"hasPart":[')):
            answers = sorted([x["acceptedAnswer"]] if isinstance(x["acceptedAnswer"], dict) else x["acceptedAnswer"],
                             key=lambda a: a["position"])
            allans = sorted(answers + x.get("suggestedAnswer", []), key=lambda a: a["position"])
            options = opts([a["text"] for a in allans])
            correct = [allans.index(a) for a in answers]
            exp = "\n".join(f"- Option {LETTERS[j]}: {a['comment']['text']}" for j, a in enumerate(allans) if a.get("comment"))
            key = norm(re.sub(r"`", "", x["text"]))[:80]
            sec = next((s for t, s in art_text if key in t), None)
            if not sec:
                print(f"  certsafari: no domain section for {cert} question {i + 1}, skipped")
                continue
            name = sec.split(": ", 1)[1]
            dom = f_domain(name) if cert == "ccar-f" else p_domain(name)
            out.append(q(cert, "certsafari", url, f"{cert}-{i + 1}", dom, html.unescape(x["text"]), options, correct, exp))
    return out


def github_olivieralter():
    repo = "OlivierAlter/Claude-Certified-Architect-Foundations-Certification-Exam"
    url = f"https://github.com/{repo}"
    md = get(f"https://raw.githubusercontent.com/{repo}/main/Claude%20Certification%20Exam.md")
    # "| 1 | Agentic Architecture & Orchestration | 27% | Q1, Q7-Q9, Q13-Q29 |"
    qdom = {}
    for num, ranges in re.findall(r"^\|\s*(\d)\s*\|[^|]+\|\s*\d+%\s*\|\s*([Q0-9 ,\-]+)\|", md, re.M):
        for part in ranges.split(","):
            a, _, b = part.strip().lstrip("Q").partition("-Q")
            for n in range(int(a), int(b or a) + 1):
                qdom[n] = F_DOMAINS[int(num) - 1]
    out = []
    for block in re.split(r"\n(?=\*\*Q\d+\.\*\*)", md):
        m = re.match(r"\*\*Q(\d+)\.\*\*\s*(.*?)\n\s*\nA\)(.*?)\*\*Correct Answer:\s*([A-D](?:\s*,\s*[A-D])*)\*\*\s*(.*)", block, re.S)
        if not m:
            continue
        n, stem, rest, ans, exp = m.groups()
        options = dict(re.findall(r"^([A-D])\)\s*(.+)$", "A)" + rest, re.M))
        exp = exp.split("\n---")[0]
        out.append(q("ccar-f", "github-olivieralter", url, f"Q{n}", qdom[int(n)], stem, options,
                     [a.strip() for a in ans.split(",")], exp))
    return out


SOURCES = {f.__name__: f for f in [open_exam_prep, szymonpaluch, claudearchitectguide, timolabs, certsafari,
                                   github_olivieralter]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in sys.argv[1:] or SOURCES:
        try:
            qs = SOURCES[name]()
        except Exception as e:  # keep going so one broken site does not block the rest
            print(f"{name}: FAILED - {e!r}")
            continue
        (OUT / f"{name}.json").write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
        by = {}
        for x in qs:
            by[x["cert"]] = by.get(x["cert"], 0) + 1
        print(f"{name}: {len(qs)} questions {by}")


if __name__ == "__main__":
    main()
