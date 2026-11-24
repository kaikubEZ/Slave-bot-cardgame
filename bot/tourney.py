"""Duplicate tournament runner: one bot in every seat of the same deals, against a fixed field.

  python3 bot/tourney.py run --bot mc --field rule --phase screen --deals 100
  python3 bot/tourney.py compare mc counter --field rule --phase screen
  python3 bot/tourney.py screen ismcts --vs mc --field search
  python3 bot/tourney.py calibrate --bot mc --secs 0.5

Results: log/tourney/<phase>/<field>/<bot>.jsonl, one line per (deal, seat). Fields: rule = counter, give_lonely,
pair_keeper; search = three mc_field bots. secs_* are wall seconds per searched decision (recorded, never used to decide)."""
import argparse, json, math, os, sys, time
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game")); sys.path.insert(0, HERE)
import run
from bots import BY_NAME
from search import MC, SEARCH, variant

LOG = os.path.join(HERE, "..", "log", "tourney")
BUDGETS = os.path.join(HERE, "budgets.json")
BASE = {"screen": 3_000_000_000, "confirm": 4_000_000_000, "calibrate": 5_000_000_000}
RULE = ["counter", "give_lonely", "pair_keeper"]

def budgets():
    try:
        with open(BUDGETS) as f: return json.load(f)
    except FileNotFoundError: return {}

B = budgets()
for _n, _c in SEARCH.items():                       # at import so pool workers see it under any start method
    if "0.5" in B.get(_n, {}): _c.work = B[_n]["0.5"]
variant(MC, "mc_field", work=B.get("mc", {}).get("0.1", MC.work // 5))
FIELDS = {"rule": RULE, "search": ["mc_field"] * 3}


def path(phase, field, bot): return os.path.join(LOG, phase, field, bot + ".jsonl")

def load(phase, field, bot):
    try:
        with open(path(phase, field, bot)) as f: return {(r["seed"], r["seat"]): r["place"] for r in map(json.loads, f)}
    except FileNotFoundError: return {}

def gap(a, b):
    """Over deals with all 4 seats in both: (n, mean a-b place, 95% CI half-width, a avg, b avg, a 1st %, b 1st %)."""
    deals = [d for d in {d for d, _ in a} & {d for d, _ in b} if all((d, s) in a and (d, s) in b for s in range(4))]
    n = len(deals)
    if n < 2: return n, 0, float("inf"), 0, 0, 0, 0
    av = [sum(a[d, s] for s in range(4)) / 4 for d in deals]; bv = [sum(b[d, s] for s in range(4)) / 4 for d in deals]
    diff = [x - y for x, y in zip(av, bv)]; m = sum(diff) / n
    ci = 1.96 * math.sqrt(sum((x - m) ** 2 for x in diff) / (n - 1) / n)
    win = lambda x: 100 * sum(x[d, s] == 1 for d in deals for s in range(4)) / (4 * n)
    return n, m, ci, sum(av) / n, sum(bv) / n, win(a), win(b)

def line(a, b, g):
    n, m, ci, aa, ba, aw, bw = g
    v = "not settled" if ci == float("inf") or abs(m) <= ci else f"{a} better" if m < 0 else f"{b} better"
    return f"{n} deals, {a} {aa:.3f}/{aw:.0f}%, {b} {ba:.3f}/{bw:.0f}%, gap {m:+.3f} ± {ci:.3f} ({v})"


def one(task):
    bot, field, seed, seat = task
    cls, ts = BY_NAME[bot], []
    class Timed(cls):                               # time only the tested seat, only decisions that had a choice
        def act(self, v):
            t = time.perf_counter(); r = cls.act(self, v)
            if len(v.legal) > 1: ts.append(time.perf_counter() - t)
            return r
    BY_NAME["_timed"] = Timed
    names = FIELDS[field][:]; names.insert(seat, "_timed")
    place = run.play_match(names, seed)["standing"].index(seat) + 1
    return {"seed": seed, "seat": seat, "place": place, "secs_max": max(ts, default=0), "secs_mean": sum(ts) / len(ts) if ts else 0,
            "n": len(ts), "secs_sum": sum(ts)}

def warm(bot, field):
    """Pool initializer: one untimed match so the JIT is hot before any measured decision."""
    old, run.TIME_LIMIT = run.TIME_LIMIT, 1e9
    try: run.play_match(FIELDS[field] + [bot], 999)
    finally: run.TIME_LIMIT = old

def play(bot, field, seeds, workers):
    """Yield results as they finish. Work overrides set on classes before this call reach workers via fork (Linux)."""
    with Pool(workers, warm, (bot, field)) as p: yield from p.imap_unordered(one, [(bot, field, d, s) for d in seeds for s in range(4)])

def run_bot(bot, field, phase, deals, workers=None):
    f = path(phase, field, bot)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    have = load(phase, field, bot)
    missing = [d for d in range(BASE[phase], BASE[phase] + deals) if not all((d, s) in have for s in range(4))]
    part = {}
    for r in play(bot, field, missing, workers or max(1, os.cpu_count() - 1)):
        part.setdefault(r["seed"], []).append({k: r[k] for k in ("seed", "seat", "place", "secs_max", "secs_mean")})
        if len(part[r["seed"]]) == 4:               # a deal's 4 seats land together, so a crash keeps finished deals
            with open(f, "a") as out: out.write("".join(json.dumps(x) + "\n" for x in part.pop(r["seed"]) if (x["seed"], x["seat"]) not in have))

def compare(a, b, field, phase): return line(a, b, gap(load(phase, field, a), load(phase, field, b)))

def screen(a, ref, field, workers=None):
    n = 0
    while n < 400:
        n += 50
        for x in (a, ref): run_bot(x, field, "screen", n, workers)
        g = gap(load("screen", field, a), load("screen", field, ref)); print(line(a, ref, g), flush=True)
        if g[2] <= 0.05 or (g[0] >= 100 and abs(g[1]) > g[2]): break

def fit(measure, work, secs, cap=0.9):
    """measure(work) -> (mean, max) seconds per searched decision. Rescale linearly to hit `secs`, then shrink until max < cap."""
    mean, _ = measure(work)
    work = max(1, round(work * secs / max(mean, 1e-9))); mean, mx = measure(work)
    for _ in range(3):
        if mx < cap: break
        work = max(1, int(work * cap * 0.98 / mx)); mean, mx = measure(work)
    return work, mean, mx

def calibrate(bot, secs, workers=None):
    cls, old, seeds = BY_NAME[bot], run.TIME_LIMIT, range(BASE["calibrate"], BASE["calibrate"] + 10)
    def measure(work):
        cls.work = work
        rs = list(play(bot, "search", seeds, workers or max(1, os.cpu_count() - 1)))
        return sum(r["secs_sum"] for r in rs) / max(1, sum(r["n"] for r in rs)), max(r["secs_max"] for r in rs)
    run.TIME_LIMIT = 30                             # measuring must not abort on a slow decision; set before the pool forks
    try: cls.work, mean, mx = fit(measure, cls.work, secs)
    finally: run.TIME_LIMIT = old
    b = budgets(); b.setdefault(bot, {})[str(secs)] = cls.work
    with open(BUDGETS, "w") as f: json.dump(b, f, indent=1)
    print(f"{bot} work={cls.work}: mean {mean:.3f}s, max {mx:.3f}s per searched decision")


CH = {"--field": {"choices": list(FIELDS)}, "--phase": {"choices": ["screen", "confirm"]}}

def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    def cmd(name, *args, **kw):
        p = sp.add_parser(name)
        for a in args: p.add_argument(a, **({"required": True} if a.startswith("--") and a not in ("--vs",) else {}), **{**CH.get(a, {}), **kw.get(a, {})})
        return p
    r = cmd("run", "--bot", "--field", "--phase", "--deals", **{"--deals": {"type": int}})
    c = cmd("compare", "a", "b", "--field", "--phase")
    s = cmd("screen", "a", "--vs", "--field"); s.set_defaults(vs="mc")
    k = cmd("calibrate", "--bot", "--secs", **{"--secs": {"type": float}})
    a = ap.parse_args()
    if a.cmd == "run": run_bot(a.bot, a.field, a.phase, a.deals)
    elif a.cmd == "compare": print(compare(a.a, a.b, a.field, a.phase))
    elif a.cmd == "screen": screen(a.a, a.vs, a.field)
    else: calibrate(a.bot, a.secs)

if __name__ == "__main__": main()
