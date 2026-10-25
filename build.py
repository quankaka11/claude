"""Merge FlashGenius (data/raw) and free-site questions (data/free) into docs/data.js.

Run after crawl.py and/or crawl_free.py. Duplicates (same normalised question text) are dropped,
keeping the first source in SOURCES order.

With CCAR_PASS set, also writes docs/data.enc.json: the encrypted copy used by the public
GitHub Pages site (docs/data.js stays local and is git-ignored).
"""
import base64
import gzip
import json
import os
import re

from crawl import CERTS, OUT_JS, RAW, ROOT

FREE = ROOT / "data" / "free"
STUDY = ROOT / "data" / "study.json"
OUT_ENC = ROOT / "docs" / "data.enc.json"  # the only data file that gets published
PBKDF2_ITER = 600_000

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
    if os.environ.get("CCAR_PASS"):
        encrypt(data, os.environ["CCAR_PASS"])
    else:
        print("CCAR_PASS not set: skipped", OUT_ENC.name, "(needed for GitHub Pages)")


def encrypt(data: dict, password: str) -> None:
    """Write the password-encrypted bundle that the public site loads (gzip + AES-256-GCM, PBKDF2 key).

    Must match unlock() in docs/app.js.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITER).derive(password.encode())
    ct = AESGCM(key).encrypt(iv, gzip.compress(json.dumps(data, ensure_ascii=False).encode()), None)
    b64 = lambda b: base64.b64encode(b).decode()
    OUT_ENC.write_text(json.dumps({"v": 1, "iter": PBKDF2_ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}),
                       encoding="utf-8")
    print("Wrote", OUT_ENC, f"({OUT_ENC.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
