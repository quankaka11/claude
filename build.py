"""Merge FlashGenius (data/raw) and free-site questions (data/free) into docs/data.js.

Run after crawl.py and/or crawl_free.py. Duplicates (same normalised question text) are dropped,
keeping the first source in SOURCES order.
"""
import json
import re

from crawl import CERTS, OUT_JS, RAW, ROOT

FREE = ROOT / "data" / "free"
STUDY = ROOT / "data" / "study.json"

# display name + homepage per source; order decides which copy wins on duplicates
SOURCES = {
    "flashgenius": ("FlashGenius", "https://flashgenius.net"),
    "claudearchitectguide": ("Claude Architect Guide", "https://claudearchitectguide.com"),
    "open-exam-prep": ("OpenExamPrep", "https://open-exam-prep.com"),
    "timolabs": ("Timo Labs", "https://www.timolabs.dev/mock-exams"),
    "certsafari": ("CertSafari", "https://www.certsafari.com"),
    "szymonpaluch": ("Szymon Paluch", "https://szymonpaluch.com/claude-certified-architect-practice-exam"),
    "github-olivieralter": ("GitHub · OlivierAlter", "https://github.com/OlivierAlter/Claude-Certified-Architect-Foundations-Certification-Exam"),
}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()[:160]


def flashgenius(slug: str) -> list:
    seen, out = set(), []
    for f in sorted(RAW.glob(f"{slug}_*.json")):
        for q in json.loads(f.read_text(encoding="utf-8")):
            if q["id"] in seen:
                continue
            seen.add(q["id"])
            keys = str(q["correctAnswer"]).replace(" ", "")
            out.append({"id": f"flashgenius:{q['id']}", "cert": slug, "source": "flashgenius",
                        "sourceUrl": f"https://flashgenius.net/sample-tests/{slug}",
                        "domain": q["domain"], "type": "multi" if "," in keys else "single",
                        "question": q["question"], "options": q["options"], "correctAnswer": keys,
                        "explanation": q["explanation"]})
    return out


def build() -> None:
    study = json.loads(STUDY.read_text(encoding="utf-8")) if STUDY.exists() else {}
    free = [q for f in sorted(FREE.glob("*.json")) for q in json.loads(f.read_text(encoding="utf-8"))]
    rank = {s: i for i, s in enumerate(SOURCES)}
    data = {}
    for slug, cfg in CERTS.items():
        pool = flashgenius(slug) + [q for q in free if q["cert"] == slug]
        pool.sort(key=lambda q: rank.get(q["source"], len(rank)))
        seen, questions = set(), []
        for q in pool:
            k = norm(q["question"]) + "|" + norm(" ".join(q.get("options", {}).values()))[:80]
            if k in seen:
                continue
            seen.add(k)
            if q["domain"] not in cfg["weights"]:
                raise ValueError(f"{q['id']}: unknown domain {q['domain']!r}")
            questions.append({k2: v for k2, v in q.items() if k2 != "cert"})
        questions.sort(key=lambda q: (q["domain"], rank.get(q["source"], 99), q["id"]))
        counts = {}
        for q in questions:
            counts[q["source"]] = counts.get(q["source"], 0) + 1
        data[slug] = {k: cfg[k] for k in ("code", "name", "exam", "weights")}
        data[slug].update(questions=questions,
                          sources={s: {"name": SOURCES[s][0], "url": SOURCES[s][1], "count": n} for s, n in counts.items()},
                          **study.get(slug, {}))
        print(f"{cfg['code']}: {len(questions)} unique questions ({len(pool) - len(questions)} duplicates dropped) {counts}")
    OUT_JS.write_text("window.CERT_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("Wrote", OUT_JS)


if __name__ == "__main__":
    build()
