#!/usr/bin/env python3
"""Build the four Jev benchmark tasks from ANY public git repo.

The point of this benchmark is that the labels are MECHANICAL -- derived from what a change
actually did, never from a model's opinion. That works on any repo with conventional commits,
so the whole thing is reproducible by anyone:

    git clone --depth 4000 https://github.com/n8n-io/n8n.git
    python3 build_public_dataset.py ./n8n

Labels:
  route   frontend | backend     <- which package tree the change actually touched
  triage  fix|feat|refactor|test <- the conventional-commit prefix the developer typed
  score   tiny|small|medium|large<- the real number of lines the diff changed
  gate    yes|no                 <- whether it touched CI / docker / migrations / build config

The model only ever sees the PROSE, with paths, filenames and giveaway terms stripped. Each task is
class-balanced so the baseline is stated rather than hidden, and a dumb keyword regex is scored
alongside in the runner so you can see what the task is worth without any model at all.
"""
import collections, json, pathlib, random, re, subprocess, sys

SEED, MAXC = 11, 1100
HERE = pathlib.Path(__file__).parent
REPO = sys.argv[1] if len(sys.argv) > 1 else "./n8n"
SEP, REC = "<<<F>>>", "<<<R>>>"

FRONTEND = ("packages/frontend", "packages/editor-ui", "packages/design-system")
BACKEND  = ("packages/cli", "packages/core", "packages/@n8n/db", "packages/@n8n/api")
RISKY    = (".github/workflows", "docker/", "Dockerfile", "migrations/", ".sql",
            "turbo.json", "pnpm-workspace", "tsconfig.build", "release", ".github/scripts")
TYPES    = ("fix", "feat", "refactor", "test")

PATH_RE = re.compile(r"\b[\w./-]*/[\w./-]+\b")
EXT_RE  = re.compile(r"\b[\w-]+\.(tsx?|jsx?|py|json|ya?ml|css|scss|sql|md|vue)\b", re.I)
TELL_RE = re.compile(r"\b(frontend|front-end|backend|back-end|editor-ui|design-system|"
                     r"vue|react|cli|server|ui|css|scss|stylesheet|component|endpoint|"
                     r"database|migration|docker|workflow file)\b", re.I)

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout

def commits(n=16000):
    raw = git("log", f"-n{n}", "--numstat", f"--pretty=format:{REC}%H{SEP}%s{SEP}%b{SEP}")
    out = []
    for chunk in raw.split(REC):
        if not chunk.strip():
            continue
        parts = chunk.split(SEP)
        if len(parts) < 4:
            continue
        sha, subj, body, stats = parts[0].strip(), parts[1], parts[2], parts[3]
        files, churn = [], 0
        for line in stats.splitlines():
            m = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if m:
                files.append(m.group(3))
                if m.group(1).isdigit():
                    churn += int(m.group(1)) + int(m.group(2) or 0)
        out.append({"sha": sha[:8], "subject": subj, "body": body, "files": files, "churn": churn})
    return out

def clean(subj, body, drop_prefix=True):
    s = re.sub(r"^[a-z]+(\([^)]*\))?!?:\s*", "", subj) if drop_prefix else subj
    s = re.sub(r"\(#\d+\)", "", s)
    t = (s + ". " + body).strip()
    t = re.sub(r"(?im)^(co-authored-by|signed-off-by|reviewed-by|refs?|closes?|fixes).*$", "", t)
    t = re.sub(r"https?://\S+", "<url>", t)
    t = PATH_RE.sub("<path>", t)
    t = EXT_RE.sub("<file>", t)
    t = TELL_RE.sub("<term>", t)
    return re.sub(r"\s+", " ", t).strip()[:MAXC]

def balanced(pool, per_cap=90):
    by = collections.defaultdict(list)
    for x in pool:
        by[x["label"]].append(x)
    rng = random.Random(SEED)
    per = min(per_cap, min(len(v) for v in by.values()))
    rows = []
    for v in by.values():
        rng.shuffle(v); rows += v[:per]
    rng.shuffle(rows)
    return rows, per

def main():
    cs = [c for c in commits() if c["files"] and len(c["body"]) > 60]
    print(f"repo: {REPO}   usable commits: {len(cs)}")
    out = {}

    pool = []
    for c in cs:
        fe = any(f.startswith(FRONTEND) for f in c["files"])
        be = any(f.startswith(BACKEND) for f in c["files"])
        if fe == be:
            continue
        t = clean(c["subject"], c["body"])
        if len(t) > 140:
            pool.append({"id": c["sha"], "label": "frontend" if fe else "backend", "text": t})
    out["route"] = balanced(pool)

    pool = []
    for c in cs:
        m = re.match(r"^([a-z]+)(\([^)]*\))?!?:", c["subject"])
        if m and m.group(1) in TYPES:
            t = clean(c["subject"], c["body"])
            if len(t) > 140:
                pool.append({"id": c["sha"], "label": m.group(1), "text": t})
    out["triage"] = balanced(pool)

    bucket = lambda ch: "tiny" if ch <= 20 else "small" if ch <= 100 else "medium" if ch <= 500 else "large"
    pool = [{"id": c["sha"], "label": bucket(c["churn"]), "churn": c["churn"],
             "text": clean(c["subject"], c["body"], drop_prefix=False)}
            for c in cs if c["churn"] > 0 and len(clean(c["subject"], c["body"])) > 140]
    out["score"] = balanced(pool)

    pool = [{"id": c["sha"],
             "label": "yes" if any(r in f for f in c["files"] for r in RISKY) else "no",
             "text": clean(c["subject"], c["body"], drop_prefix=False)}
            for c in cs if len(clean(c["subject"], c["body"])) > 140]
    out["gate"] = balanced(pool)

    for name, (rows, per) in out.items():
        n_cls = len({r["label"] for r in rows})
        leaks = [r["id"] for r in rows if TELL_RE.search(r["text"])]
        assert not leaks, f"{name}: leakage survived in {leaks[:3]}"
        (HERE / f"public_{name}.json").write_text(json.dumps(rows, indent=1))
        print(f"  {name:7s} {len(rows):4d} rows · {per}/class · {n_cls} classes · baseline {1/n_cls:.1%}")
    print("\nwrote public_{route,triage,score,gate}.json")

if __name__ == "__main__":
    main()
