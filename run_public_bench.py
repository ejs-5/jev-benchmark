#!/usr/bin/env python3
"""Run Jev + frontier models over the four public-repo tasks.

Everything here is reproducible: the datasets come from a public git repo (build_public_dataset.py),
the labels are mechanical, and a dumb keyword regex is scored alongside so you can see what each
task is worth with no model at all. An unanswered row counts as WRONG, never dropped.
"""
import json, os, pathlib, re, statistics as st, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).parent
KEY  = os.environ["OPENROUTER_API_KEY"]
DEC  = "https://openrouter.ai/api/alpha/decisions"
CHAT = "https://openrouter.ai/api/v1/chat/completions"
JEV  = "typesafe/jev-1.13"
FRONTIER = ["openai/gpt-5.6-terra", "anthropic/claude-opus-5"]
LEVELS = ["tiny", "small", "medium", "large"]

TASKS = {
 "route": {"kind":"choice","file":"public_route.json",
   "ask":"Is this engineering work about the user interface or the server?",
   "criteria":{"frontend":"Work on the user interface - screens, components, dialogs, styling, what a person sees and clicks.",
               "backend":"Work on the server - API endpoints, database, schemas, background jobs, logic a user never sees."}},
 "triage": {"kind":"choice","file":"public_triage.json",
   "ask":"What kind of change is this developer describing?",
   "criteria":{"fix":"Repairing something that was broken or behaving wrongly.",
               "feat":"Adding a new capability that did not exist before.",
               "refactor":"Restructuring existing code without changing what it does.",
               "test":"Adding or changing automated tests only."}},
 "score": {"kind":"score","file":"public_score.json",
   "ask":"How large is this code change?",
   "criteria":["A one-line tweak (under 20 lines changed)","A small focused change (20-100 lines)",
               "A medium multi-file change (100-500 lines)","A large sweeping change (over 500 lines)"]},
 "gate": {"kind":"noul","file":"public_gate.json",
   "ask":"Could this change break production or the build if it went wrong? "
         "(true for CI pipelines, docker, database migrations, release/build configuration)"},
}
KEYWORDS = {
 "route": lambda t: "frontend" if re.search(r"\b(dialog|button|screen|page|click|modal|layout|styling|scroll|icon|canvas|node panel|view)\b",t,re.I) else "backend",
 "triage": lambda t: ("test" if re.search(r"\b(test|spec|coverage|assert)\b",t,re.I)
              else "refactor" if re.search(r"\b(refactor|restructur|clean ?up|rename|extract|simplif)\b",t,re.I)
              else "fix" if re.search(r"\b(fix|bug|broken|regress|wrong|fail|crash|error)\b",t,re.I) else "feat"),
 "score": lambda t: LEVELS[min(3, len(t)//300)],
 "gate":  lambda t: "yes" if re.search(r"\b(ci|pipeline|docker|migration|release|build|deploy|workflow)\b",t,re.I) else "no",
}

def post(url, payload, timeout=240):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type":"application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), time.perf_counter()-t0, None
    except urllib.error.HTTPError as e:
        return None, time.perf_counter()-t0, f"HTTP {e.code}: {e.read()[:160]!r}"
    except Exception as e:
        return None, time.perf_counter()-t0, repr(e)

def jev_q(sp):
    k = sp["kind"]
    if k == "noul": return {"type":"noul","instructions":sp["ask"]}
    return {"type":k,"instructions":sp["ask"],"criteria":sp["criteria"]}

def jev_pred(a, kind):
    if kind == "choice": return a["choice"], a.get("confidence")
    if kind == "score":
        return LEVELS[max(0,min(3,int(round(a["score"]))))], a.get("confidence")
    n = a["noul"]; return ("yes" if n>=.5 else "no"), abs(n-.5)*2

def run_jev(task, sp, rows):
    out=[]
    for i,r in enumerate(rows,1):
        b,dt,err = post(DEC, {"model":JEV,"state":r["text"],"questions":{"q":jev_q(sp)}})
        rec={"id":r["id"],"label":r["label"],"latency_s":dt,"error":err}
        if b:
            p,c = jev_pred(b["answers"]["q"], sp["kind"])
            rec |= {"pred":p,"confidence":c,"cost":b.get("usage",{}).get("cost",0.0)}
        out.append(rec)
        if i%40==0 or i==len(rows): print(f"    jev/{task} {i}/{len(rows)}", flush=True)
    return out

def fprompt(sp):
    k = sp["kind"]
    if k=="choice":
        opts=" ".join(f'"{a}" = {b}' for a,b in sp["criteria"].items()); space=" | ".join(f'"{x}"' for x in sp["criteria"])
    elif k=="score":
        opts=" ".join(f'"{LEVELS[i]}" = {d}' for i,d in enumerate(sp["criteria"])); space=" | ".join(f'"{x}"' for x in LEVELS)
    else:
        opts=sp["ask"]; space='"yes" | "no"'
    return f'{opts}\nAnswer ONLY with compact JSON: {{"answer": {space}, "confidence": <0.0-1.0>}}. No other text.'

def one_f(model, sp, r):
    b,dt,err = post(CHAT, {"model":model,"max_tokens":600,"temperature":0,
        "messages":[{"role":"system","content":fprompt(sp)},{"role":"user","content":f"{sp['ask']}\n\n{r['text']}"}]})
    rec={"id":r["id"],"label":r["label"],"latency_s":dt,"error":err}
    if b:
        rec["cost"]=(b.get("usage") or {}).get("cost",0.0)
        try:
            txt=(b["choices"][0]["message"].get("content") or "").strip()
            txt=txt[txt.find("{"):txt.rfind("}")+1]
            j=json.loads(txt)
            rec |= {"pred":str(j.get("answer","")).lower().strip(),"confidence":float(j.get("confidence",0))}
        except Exception as e: rec["error"]=f"parse: {e!r}"
    return rec

def summarize(name, task, recs, rows):
    valid={r["label"] for r in rows}
    ok=[r for r in recs if r.get("pred") in valid]
    hit=sum(1 for r in ok if r["pred"]==r["label"])
    lat=sorted(r["latency_s"] for r in recs if not r.get("error"))
    cost=sum(r.get("cost") or 0 for r in recs)
    b={}
    for r in ok:
        c=r.get("confidence")
        if c is None: continue
        k="1.00" if c>=.999 else f"{int(c*10)/10:.1f}"
        b.setdefault(k,[]).append(r["pred"]==r["label"])
    return {"model":name,"task":task,"n":len(recs),"answered":len(ok),
            "accuracy":hit/len(recs) if recs else 0,
            "median_latency_s":st.median(lat) if lat else 0,
            "cost_per_decision_usd":cost/len(recs) if recs else 0,
            "total_cost_usd":cost,"unanswered":len(recs)-len(ok),
            "calibration":{k:{"n":len(v),"accuracy":sum(v)/len(v)} for k,v in sorted(b.items())}}

if __name__ == "__main__":
    raw, summ = {}, []
    for task, sp in TASKS.items():
        rows=json.loads((HERE/sp["file"]).read_text())
        base=sum(1 for r in rows if KEYWORDS[task](r["text"])==r["label"])/len(rows)
        print(f"\n### {task}: n={len(rows)} | keyword baseline {base:.1%}", flush=True)
        summ.append({"model":"keyword-regex (baseline)","task":task,"n":len(rows),"accuracy":base,
                     "median_latency_s":0,"cost_per_decision_usd":0,"total_cost_usd":0,
                     "unanswered":0,"answered":len(rows),"calibration":{}})
        raw[f"{task}|jev"]=run_jev(task,sp,rows)
        summ.append(summarize(JEV,task,raw[f"{task}|jev"],rows))
        for m in FRONTIER:
            print(f"    {m}/{task} ...", flush=True)
            with ThreadPoolExecutor(max_workers=6) as ex:
                recs=list(ex.map(lambda r: one_f(m,sp,r), rows))
            raw[f"{task}|{m}"]=recs; summ.append(summarize(m,task,recs,rows))
    (HERE/"public_raw.json").write_text(json.dumps(raw,indent=1))
    (HERE/"public_summary.json").write_text(json.dumps(summ,indent=1))
    print("\n"+"="*94)
    print(f"{'task':8s} {'model':28s} {'acc':>7s} {'median':>9s} {'$/decision':>12s} {'unans':>6s}")
    print("-"*94)
    for s in summ:
        print(f"{s['task']:8s} {s['model']:28s} {s['accuracy']:6.1%} "
              f"{s['median_latency_s']*1000:8.0f}ms {s['cost_per_decision_usd']:12.6f} {s['unanswered']:6d}")
    print("="*94)
    print(f"total spend: ${sum(s['total_cost_usd'] for s in summ):.4f}")
