# jev-benchmark

An independent benchmark of [TypeSafe's Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) on **868 real decisions** from a public repository, with labels that are **mechanical rather than model-generated**.

Jev is a non-autoregressive model: instead of writing text, it returns a typed decision with a confidence score. TypeSafe's own evaluation grades it against the averaged opinions of two other frontier models. This one doesn't grade against any model at all.

## Why the labels are the point

Every label here comes from what a change **actually did**, recoverable from git:

| Task | Question the model is asked | Where the label comes from |
|---|---|---|
| **Route** | Is this work about the UI or the server? | which package tree the change touched |
| **Triage** | Is this a fix, feature, refactor or test? | the conventional-commit prefix the developer typed |
| **Size** | How big is this change? | the real number of lines the diff changed |
| **Risk** | Could this break production or the build? | whether it touched CI / docker / migrations / build config |

The model only ever sees the commit **prose**, with paths, filenames and giveaway terms stripped. Every task is class-balanced so the chance baseline is stated rather than hidden, a dumb keyword regex is scored alongside so you can see what each task is worth with no model at all, and an unanswered row counts as **wrong** rather than being dropped.

Source corpus: [n8n](https://github.com/n8n-io/n8n) — 17,468 commits, disciplined conventional commits, clear frontend/backend split. Nothing here is private; you can rebuild the datasets yourself.

## Results

| Task | n | chance | keyword regex | Jev | GPT-5.6 Terra | Claude Opus 5 |
|---|---|---|---|---|---|---|
| Route | 180 | 50% | 65.0% | **85.6%** | 88.3% | 90.6% |
| Triage | 148 | 25% | 40.5% | **70.9%** | 73.0% | 80.4% |
| Size | 360 | 25% | 25.3% | **37.2%** | 40.0% | 45.8% |
| Risk | 180 | 50% | 60.6% | **63.9%** | 66.1% | 80.0% |

### ⚠️ We tried to replicate our own headline finding. It did not hold.

This benchmark exists because we ran an earlier version on a **private** repo and published a video about it. The headline finding there was a *complexity cliff*: Jev scored 86.0% on a two-option task and collapsed to 57.7% on a four-option one — a 29.8-point gap against Claude Opus 5. We explained it as a property of how Jev works.

Re-run on this public corpus, **that gap is 9.5 points, not 29.8.** Jev scores 70.9% on the four-option task here.

| Task | gap, private repo | gap, n8n | |
|---|---|---|---|
| Route | -3.5 | -5.0 | replicated |
| Triage | -29.8 | -9.5 | **did not replicate** |
| Size | -8.6 | -8.6 | replicated |
| Risk | -4.7 | -16.1 | shifted the other way |

**So the cliff was a property of that corpus, not of the model.** The private repo's commit notes are long internal engineering prose (~1,100 chars); n8n's are short and disciplined (~300). Jev is documented as sensitive to what is in the state, and that is the most likely explanation — but we did not establish it, so treat it as a hypothesis.

We are publishing this because a benchmark you only publish when it agrees with you is not a benchmark. The video is already out with the stronger claim; it now carries a correction.

### Speed and cost

| Task | Jev median | Opus 5 median | Jev $/decision | Opus 5 $/decision | faster | cheaper |
|---|---|---|---|---|---|---|
| Route | 424 ms | 2405 ms | $0.000018 | $0.002210 | 5.7x | 120x |
| Triage | 411 ms | 2860 ms | $0.000019 | $0.003254 | 7.0x | 171x |
| Size | 432 ms | 2462 ms | $0.000018 | $0.002874 | 5.7x | 159x |
| Risk | 429 ms | 5055 ms | $0.000016 | $0.003806 | 11.8x | 242x |

Total cost of the entire run, all four tasks and three models: **$3.35**.

### Calibration — this one replicated, and got more interesting

The direction of Jev's miscalibration depends on the question type. On **Choice and Score** questions it is over-confident; on **Noul** (true/false) it is markedly *under*-confident — it says 0.2 and is right 76% of the time. That matches an independent audit which found calibration holding on a boolean task and disagreed with our original over-confidence finding. Both can be true, because they were measuring different primitives.

Jev returns a confidence with every answer. The deployment recipe everyone repeats is *route below a threshold to a human, above it to code* — which only works if the number is calibrated. Binned by what Jev claimed:

| Task | confidence bucket | n | actually right |
|---|---|---|---|
| Route | 0.8–0.9 | 9 | 100.0% |
| Route | 0.9–1.0 | 50 | 86.0% |
| Route | 1.00 (no doubt at all) | 94 | 92.6% |
| Triage | 0.6–0.7 | 16 | 62.5% |
| Triage | 0.7–0.8 | 10 | 90.0% |
| Triage | 0.8–0.9 | 17 | 52.9% |
| Triage | 0.9–1.0 | 35 | 74.3% |
| Triage | 1.00 (no doubt at all) | 53 | 84.9% |
| Size | 0.3–0.4 | 11 | 27.3% |
| Size | 0.4–0.5 | 17 | 17.6% |
| Size | 0.5–0.6 | 60 | 33.3% |
| Size | 0.6–0.7 | 70 | 30.0% |
| Size | 0.7–0.8 | 66 | 36.4% |
| Size | 0.8–0.9 | 55 | 47.3% |
| Size | 0.9–1.0 | 75 | 48.0% |
| Risk | 0.0–0.1 | 30 | 50.0% |
| Risk | 0.1–0.2 | 31 | 51.6% |
| Risk | 0.2–0.3 | 25 | 76.0% |
| Risk | 0.3–0.4 | 21 | 57.1% |
| Risk | 0.4–0.5 | 27 | 66.7% |
| Risk | 0.5–0.6 | 22 | 68.2% |
| Risk | 0.6–0.7 | 11 | 81.8% |
| Risk | 0.7–0.8 | 10 | 90.0% |

### Structured output

| Model | unparseable / refused |
|---|---|
| Jev | 1 / 868 |
| GPT-5.6 Terra | 0 / 868 |
| Claude Opus 5 | 1 / 868 |

Jev cannot return a value outside the schema, so this is structurally zero for it. Whether that's a *differentiator* depends on what the others do — see the table.


The worst case here is the Score task: Jev claims 0.9 on 75 decisions and is right 48.0% of them — a 47-point gap. The deployment recipe everyone repeats (route below a threshold to a human) does not survive that without measuring it on your own data first.

## Reproduce it

```bash
git clone --depth 16000 https://github.com/n8n-io/n8n.git
python3 build_public_dataset.py ./n8n          # rebuilds the four task files
export OPENROUTER_API_KEY=sk-...
python3 run_public_bench.py                    # ~20 min
```

## Honest limits

- **One codebase.** Everything here is n8n's commit prose. A different project's writing style could move these numbers, and n8n's contributors write unusually disciplined commit messages.
- **The size task is close to unusable for everyone.** Judging how many lines a diff touched from its description is hard; read that row as a fact about the task, not about any model.
- **Calibration is task-dependent and contested.** At least one independent audit reports Jev's confidence holding up on a different kind of task. Measure it on your own data.
- **We are not neutral.** This was built for a video. The code and data are here so you don't have to take our word for any of it.

MIT licensed. Corrections welcome — open an issue and we'll fix the numbers and say we did.
