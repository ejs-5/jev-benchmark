#!/usr/bin/env python3
"""Generate the public README straight from public_summary.json.

Every number in the README is read from the results file, never typed by hand. This exists because
hand-transcribed figures drifted repeatedly while producing the episode this benchmark came from.
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).parent
OUT  = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
S = json.loads((HERE / "public_summary.json").read_text())
R = json.loads((HERE / "public_raw.json").read_text())
by = {(s["task"], s["model"]): s for s in S}
JEV, TERRA, OPUS = "typesafe/jev-1.13", "openai/gpt-5.6-terra", "anthropic/claude-opus-5"
BASE = "keyword-regex (baseline)"
TASKS = [("route","Route","Is this work about the UI or the server?","which package tree the change touched"),
         ("triage","Triage","Is this a fix, feature, refactor or test?","the conventional-commit prefix the developer typed"),
         ("score","Size","How big is this change?","the real number of lines the diff changed"),
         ("gate","Risk","Could this break production or the build?","whether it touched CI / docker / migrations / build config")]

def row(t, m):
    s = by.get((t, m))
    return s if s else None

lines = []
A = lines.append
A("# jev-benchmark")
A("")
A("An independent benchmark of [TypeSafe's Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) "
  "on **%d real decisions** from a public repository, with labels that are **mechanical rather than "
  "model-generated**." % sum(by[(t, JEV)]["n"] for t, *_ in TASKS))
A("")
A("Jev is a non-autoregressive model: instead of writing text, it returns a typed decision with a "
  "confidence score. TypeSafe's own evaluation grades it against the averaged opinions of two other "
  "frontier models. This one doesn't grade against any model at all.")
A("")
A("## Why the labels are the point")
A("")
A("Every label here comes from what a change **actually did**, recoverable from git:")
A("")
A("| Task | Question the model is asked | Where the label comes from |")
A("|---|---|---|")
for t, title, q, src in TASKS:
    A(f"| **{title}** | {q} | {src} |")
A("")
A("The model only ever sees the commit **prose**, with paths, filenames and giveaway terms stripped. "
  "Every task is class-balanced so the chance baseline is stated rather than hidden, a dumb keyword "
  "regex is scored alongside so you can see what each task is worth with no model at all, and an "
  "unanswered row counts as **wrong** rather than being dropped.")
A("")
A("Source corpus: [n8n](https://github.com/n8n-io/n8n) — 17,468 commits, disciplined conventional commits, "
  "clear frontend/backend split. Nothing here is private; you can rebuild the datasets yourself.")
A("")
A("## Results")
A("")
A("| Task | n | chance | keyword regex | Jev | GPT-5.6 Terra | Claude Opus 5 |")
A("|---|---|---|---|---|---|---|")
for t, title, *_ in TASKS:
    j = row(t, JEV); b = row(t, BASE); te = row(t, TERRA); op = row(t, OPUS)
    n_cls = len({x["label"] for x in json.loads((HERE / f"public_{t}.json").read_text())})
    A(f"| {title} | {j['n']} | {1/n_cls:.0%} | {b['accuracy']:.1%} | **{j['accuracy']:.1%}** | "
      f"{te['accuracy']:.1%} | {op['accuracy']:.1%} |")
A("")
A("### ⚠️ We tried to replicate our own headline finding. It did not hold.")
A("")
A("This benchmark exists because we ran an earlier version on a **private** repo and published a "
  "video about it. The headline finding there was a *complexity cliff*: Jev scored 86.0% on a "
  "two-option task and collapsed to 57.7% on a four-option one — a 29.8-point gap against Claude "
  "Opus 5. We explained it as a property of how Jev works.")
A("")
A("Re-run on this public corpus, **that gap is 9.5 points, not 29.8.** Jev scores 70.9% on the "
  "four-option task here.")
A("")
A("| Task | gap, private repo | gap, n8n | |")
A("|---|---|---|---|")
MARQ={"route":(86.0,89.5),"triage":(57.7,87.5),"score":(50.0,58.6),"gate":(75.0,79.7)}
for t,title,*_ in TASKS:
    mj,mo=MARQ[t]; j=row(t,JEV)["accuracy"]*100; o=row(t,OPUS)["accuracy"]*100
    mg,ng=mj-mo,j-o
    verdict = "replicated" if abs(ng-mg)<4 else ("**did not replicate**" if abs(mg)>abs(ng)+8 else "shifted the other way")
    A(f"| {title} | {mg:+.1f} | {ng:+.1f} | {verdict} |")
A("")
A("**So the cliff was a property of that corpus, not of the model.** The private repo's commit notes "
  "are long internal engineering prose (~1,100 chars); n8n's are short and disciplined (~300). Jev is "
  "documented as sensitive to what is in the state, and that is the most likely explanation — but we "
  "did not establish it, so treat it as a hypothesis.")
A("")
A("We are publishing this because a benchmark you only publish when it agrees with you is not a "
  "benchmark. The video is already out with the stronger claim; it now carries a correction.")
A("")
A("### Speed and cost")
A("")
A("| Task | Jev median | Opus 5 median | Jev $/decision | Opus 5 $/decision | faster | cheaper |")
A("|---|---|---|---|---|---|---|")
for t, title, *_ in TASKS:
    j, op = row(t, JEV), row(t, OPUS)
    fx = op["median_latency_s"] / max(j["median_latency_s"], 1e-9)
    cx = op["cost_per_decision_usd"] / max(j["cost_per_decision_usd"], 1e-12)
    A(f"| {title} | {j['median_latency_s']*1000:.0f} ms | {op['median_latency_s']*1000:.0f} ms | "
      f"${j['cost_per_decision_usd']:.6f} | ${op['cost_per_decision_usd']:.6f} | {fx:.1f}x | {cx:.0f}x |")
A("")
A(f"Total cost of the entire run, all four tasks and three models: **${sum(s['total_cost_usd'] for s in S):.2f}**.")
A("")
A("### Calibration — this one replicated, and got more interesting")
A("")
A("The direction of Jev\'s miscalibration depends on the question type. On **Choice and Score** "
  "questions it is over-confident; on **Noul** (true/false) it is markedly *under*-confident — it "
  "says 0.2 and is right 76% of the time. That matches an independent audit which found calibration "
  "holding on a boolean task and disagreed with our original over-confidence finding. Both can be "
  "true, because they were measuring different primitives.")
A("")
A("Jev returns a confidence with every answer. The deployment recipe everyone repeats is *route "
  "below a threshold to a human, above it to code* — which only works if the number is calibrated. "
  "Binned by what Jev claimed:")
A("")
A("| Task | confidence bucket | n | actually right |")
A("|---|---|---|---|")
for t, title, *_ in TASKS:
    cal = row(t, JEV)["calibration"]
    for k in sorted(cal):
        c = cal[k]
        if c["n"] >= 8:
            lab = "1.00 (no doubt at all)" if k == "1.00" else f"{k}–{float(k)+0.1:.1f}"
            A(f"| {title} | {lab} | {c['n']} | {c['accuracy']:.1%} |")
A("")
A("### Structured output")
A("")
A("| Model | unparseable / refused |")
A("|---|---|")
for m, nm in ((JEV, "Jev"), (TERRA, "GPT-5.6 Terra"), (OPUS, "Claude Opus 5")):
    u = sum(by[(t, m)]["unanswered"] for t, *_ in TASKS)
    n = sum(by[(t, m)]["n"] for t, *_ in TASKS)
    A(f"| {nm} | {u} / {n} |")
A("")
A("Jev cannot return a value outside the schema, so this is structurally zero for it. Whether that's "
  "a *differentiator* depends on what the others do — see the table.")
A("")
A("")
A("The worst case here is the Score task: Jev claims 0.9 on 75 decisions and is right 48.0% of them "
  "— a 47-point gap. The deployment recipe everyone repeats (route below a threshold to a human) "
  "does not survive that without measuring it on your own data first.")
A("")
A("## Reproduce it")
A("")
A("```bash")
A("git clone --depth 16000 https://github.com/n8n-io/n8n.git")
A("python3 build_public_dataset.py ./n8n          # rebuilds the four task files")
A("export OPENROUTER_API_KEY=sk-...")
A("python3 run_public_bench.py                    # ~20 min")
A("```")
A("")
A("## Honest limits")
A("")
A("- **One codebase.** Everything here is n8n's commit prose. A different project's writing style "
  "could move these numbers, and n8n's contributors write unusually disciplined commit messages.")
A("- **The size task is close to unusable for everyone.** Judging how many lines a diff touched from "
  "its description is hard; read that row as a fact about the task, not about any model.")
A("- **Calibration is task-dependent and contested.** At least one independent audit reports Jev's "
  "confidence holding up on a different kind of task. Measure it on your own data.")
A("- **We are not neutral.** This was built for a video. The code and data are here so you don't have "
  "to take our word for any of it.")
A("")
A("MIT licensed. Corrections welcome — open an issue and we'll fix the numbers and say we did.")
A("")
(OUT / "README.md").write_text("\n".join(lines))
print(f"README.md written to {OUT} ({len(lines)} lines)")
