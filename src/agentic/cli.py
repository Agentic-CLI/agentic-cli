"""agentic — a supervisory framework for agentic development.

Define (bundle) → Compile (project) → Supervise (gate) → Record (ledger).
"""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__, _yaml, bundle, deliver, gate, ledger, observe, projector, resolve, run
from .util import find_project_root

C = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m", "b": "\033[34m", "d": "\033[2m", "0": "\033[0m"}


def _c(key, s):
    return f"{C[key]}{s}{C['0']}" if sys.stdout.isatty() else s


def _root_or_die():
    root = find_project_root()
    if not root:
        print(_c("r", "not an agentic project (no .agentic/). Run `agentic init` first."))
        sys.exit(1)
    return root


def cmd_init(args):
    root = os.getcwd()
    if os.path.exists(bundle.bundle_path(root)) and not args.force:
        print(_c("y", f"bundle already exists at {bundle.BUNDLE_REL} (use --force to overwrite)"))
        return 0
    name = args.name or os.path.basename(root)
    data = bundle.default(name)
    bundle.save(root, data)
    os.makedirs(os.path.join(root, ".agentic", "ledger"), exist_ok=True)
    engine = "PyYAML" if _yaml.USING_PYYAML else "built-in yaml fallback (zero deps)"
    print(_c("g", f"✓ initialized agentic bundle for '{name}'") + _c("d", f"  [{engine}]"))
    print(f"  {bundle.BUNDLE_REL}")
    print(f"\nNext: {_c('b', 'agentic project')}  # compile into .claude/ + AGENTS.md")
    return 0


def cmd_project(args):
    root = _root_or_die()
    data = resolve.effective_bundle(root)
    errs = bundle.validate(data)
    if errs:
        print(_c("r", "bundle invalid:"))
        for e in errs:
            print("  - " + e)
        return 1
    result = projector.project(root, data)
    print(_c("g", f"✓ projected {len(result['files'])} files:"))
    for rel in result["files"]:
        print("  " + rel)
    print(_c("d", "\n  hooks wired: PreToolUse(Edit|Write) → agentic gate"))
    return 0


def cmd_gate(args):
    return gate.run(args)


def cmd_doctor(args):
    root = _root_or_die()
    data = resolve.effective_bundle(root)
    errs = bundle.validate(data)
    for e in errs:
        print(_c("r", "bundle: " + e))
    drift = projector.check_drift(root, data)
    ok, count, bad = ledger.verify(root)
    if drift:
        print(_c("y", "drift (regenerate with `agentic project`):"))
        for d in drift:
            print("  - " + d)
    else:
        print(_c("g", "✓ generated files in sync with bundle"))
    if ok:
        print(_c("g", f"✓ ledger intact ({count} entries, hash chain valid)"))
    else:
        print(_c("r", f"✗ ledger tampered at seq {bad}"))
    return 0 if (not errs and not drift and ok) else 1


def cmd_ledger(args):
    root = _root_or_die()
    if getattr(args, "follow", False):
        print(_c("d", "following ledger — Ctrl-C to stop"))

        def _line(e):
            dec = e.get("decision", "")
            col = "r" if dec == "block" else "g" if dec in ("allow", "observed", "advance", "merged") else "y"
            print(f"{_c('d', e.get('ts',''))}  {_c('b', e['run_id'][:10])}  "
                  f"{e.get('event',''):<14} {_c(col, dec):<9} {e.get('subject',{}).get('ref','')}")

        ledger.follow(root, _line)
        return 0
    es = ledger.entries(root, args.run)
    if not es:
        print(_c("d", "ledger empty"))
        return 0
    for e in es:
        dec = e.get("decision", "")
        col = "r" if dec == "block" else "g" if dec in ("allow", "observed") else "y"
        ref = e.get("subject", {}).get("ref", "")
        print(
            f"{_c('d', e.get('ts',''))}  {_c('b', e['run_id'][:10])}  "
            f"{e.get('event',''):<14} {_c(col, dec):<8} {e.get('sensitivity','') :<9} {ref}"
        )
    ok, count, bad = ledger.verify(root)
    tag = _c("g", "chain valid") if ok else _c("r", f"chain broken @ {bad}")
    print(_c("d", f"\n{count} entries · {tag}"))
    return 0


def cmd_trace(args):
    root = _root_or_die()
    es = ledger.entries(root, args.run_id)
    if not es:
        print(_c("y", f"no entries for run {args.run_id}"))
        return 1
    print(_c("b", f"run {args.run_id}") + _c("d", f"  ({len(es)} events)"))
    for e in es:
        print(f"  {e.get('ts','')}  {e.get('event',''):<14} {e.get('decision',''):<8} "
              f"{e.get('subject',{}).get('ref','')}")
    return 0


def cmd_observe(args):
    root = _root_or_die()
    n = observe.from_git(root, args.since)
    print(_c("g", f"✓ observed {n} new commits into the ledger") if n
          else _c("d", "no new commits to observe"))
    return 0


def cmd_relay(args):
    root = _root_or_die()
    if args.relay_cmd == "list":
        items = ledger.list_relays(root)
        if not items:
            print(_c("d", "no relay items"))
            return 0
        for it in items:
            col = "y" if it["status"] == "pending" else "g" if it["status"] == "resolved" else "r"
            print(f"{_c('b', it['relay_id'])}  {_c(col, it['status']):<10} {it['reason']}")
        return 0
    if args.relay_cmd == "resolve":
        decision = "reject" if args.reject else ("approve_with_edit" if args.edit else "approve")
        item = ledger.resolve_relay(root, args.relay_id, decision, args.approver or "human", args.reason or "")
        if not item:
            print(_c("r", f"no relay {args.relay_id}"))
            return 1
        print(_c("g", f"✓ {args.relay_id} → {item['status']} ({decision})"))
        return 0
    return 1


def cmd_add(args):
    root = _root_or_die()
    data = bundle.load(root)
    extends = data.setdefault("extends", []) or []
    if args.source not in extends:
        extends.append(args.source)
    data["extends"] = extends
    bundle.save(root, data)
    # resolve to discover the persona id, then wire a `use:` role
    repo, subpath, ref = resolve.parse_source(args.source)
    dest, _sha = resolve.fetch(repo, ref)
    defn = _yaml.load(open(os.path.join(dest, subpath)).read()) or {}
    pid = defn.get("id")
    if pid and defn.get("kind", "persona") == "persona":
        roles = data.setdefault("sdlc", {}).setdefault("roles", [])
        if not any(isinstance(r, dict) and (r.get("use") == pid or r.get("id") == pid) for r in roles):
            roles.append({"use": pid})
        bundle.save(root, data)
    resolve.effective_bundle(root)  # write the lockfile
    print(_c("g", f"✓ added {args.source}"))
    if pid:
        print(f"  persona {_c('b', pid)} wired — run {_c('b', 'agentic project')} to compile it in")
    return 0


def cmd_lock(args):
    root = _root_or_die()
    resolve.effective_bundle(root, update=args.update)
    srcs = resolve.load_lock(root).get("sources", {})
    if not srcs:
        print(_c("d", "no extends: sources to lock"))
        return 0
    print(_c("g", f"✓ locked {len(srcs)} source(s):"))
    for entry, meta in srcs.items():
        print(f"  {entry}\n    {_c('d', '→ ' + meta['resolved_commit'][:12])}")
    return 0


def _find_run(root, rid):
    if run.load(root, rid):
        return rid
    for x in run.list_runs(root):
        if x["run_id"].startswith(rid):
            return x["run_id"]
    return None


def cmd_run(args):
    root = _root_or_die()
    if args.run_cmd == "start":
        r = run.start(root, args.title)
        print(_c("g", f"✓ run {r['run_id']} started") + _c("d", f"  phase: {r['phase']}"))
        print(f"  attach artifacts, then: {_c('b', 'agentic run advance ' + r['run_id'][:10])}")
        return 0
    if args.run_cmd == "list":
        rs = run.list_runs(root)
        if not rs:
            print(_c("d", "no runs — start one with `agentic run start \"<title>\"`"))
            return 0
        for r in rs:
            col = "g" if r["status"] == "done" else "y" if r["status"] == "awaiting_relay" else "b"
            print(f"{_c('b', r['run_id'][:10])}  {_c(col, r['status']):<16} {r['phase']:<10} {r.get('title', '')}")
        return 0
    rid = _find_run(root, args.run_id)
    if not rid:
        print(_c("r", f"no such run: {args.run_id}"))
        return 1
    if args.run_cmd == "status":
        r = run.load(root, rid)
        print(_c("b", r["run_id"]) + f"  · {r['status']} · phase {r['phase']}")
        print("  title:     " + r.get("title", ""))
        print("  artifacts: " + (", ".join(r["artifacts"]) or "—"))
        return 0
    if args.run_cmd == "artifact":
        r = run.submit_artifact(root, rid, args.name, args.ref)
        print(_c("g", f"✓ artifact '{args.name}' recorded") + _c("d", f"  ({r['run_id'][:10]} · phase {r['phase']})"))
        return 0
    if args.run_cmd == "advance":
        res = run.advance(root, rid)
        if res.get("ok"):
            if res.get("status") == "done":
                print(_c("g", "✓ run complete — every phase passed its gate"))
            else:
                g = f" (gate {res['gate']})" if res.get("gate") else ""
                print(_c("g", f"✓ advanced {res.get('from')} → {res['phase']}") + _c("d", g))
            return 0
        col = "y" if res.get("status") == "awaiting_relay" else "r"
        print(_c(col, "✗ " + res.get("reason", "blocked")))
        return 2
    return 1


def cmd_plan(args):
    root = _root_or_die()
    rid = _find_run(root, args.run_id)
    if not rid:
        print(_c("r", f"no such run: {args.run_id}"))
        return 1
    r = run.load(root, rid)
    path = os.path.join(root, ".agentic", "runs", rid + ".plan.md")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(f"# Plan — {r.get('title', '')}\n\n## Approach\n\n## Steps\n\n## Risks & rollback\n\n## Test strategy\n")
    run.submit_artifact(root, rid, "plan_note", os.path.relpath(path, root))
    print(_c("g", f"✓ plan scaffolded → {os.path.relpath(path, root)}") + _c("d", "  (artifact 'plan_note' recorded — Definition of Ready)"))
    return 0


def cmd_status(args):
    root = _root_or_die()
    data = resolve.effective_bundle(root)
    sdlc = data.get("sdlc", {})
    print(_c("b", data.get("name", "?")) + _c("d", " — agentic status"))
    print(f"  roles {len(sdlc.get('roles', []))} · phases {len(sdlc.get('lifecycle', {}).get('phases', []))} · standards {len(sdlc.get('standards', []))}")
    rs = run.list_runs(root)
    counts = {k: sum(1 for r in rs if r["status"] == k) for k in ("active", "awaiting_relay", "done")}
    print(f"  runs: {counts['active']} active · {counts['awaiting_relay']} awaiting relay · {counts['done']} done")
    pending = sum(1 for x in ledger.list_relays(root) if x["status"] == "pending")
    ok, count, bad = ledger.verify(root)
    print(f"  pending relays: {pending}")
    print(f"  ledger: {count} events · " + (_c("g", "chain valid") if ok else _c("r", f"tampered @ {bad}")))
    return 0


def cmd_mcp(args):
    from . import mcp
    mcp.serve(find_project_root() or os.getcwd())
    return 0


def _find_epic(root, eid):
    e = deliver.load(root, eid)
    if e:
        return e
    return next((x for x in deliver.list_epics(root) if x["epic_id"].startswith(eid)), None)


def cmd_deliver(args):
    root = _root_or_die()
    try:
        if args.deliver_cmd == "start":
            epic = deliver.start(root, args.titles)
            print(_c("g", f"✓ epic {epic['epic_id'][:10]} — {len(epic['items'])} items in isolated worktrees"))
            for it in epic["items"]:
                print(f"  {_c('b', it['run_id'][:10])}  {it['branch']:<18} {os.path.relpath(it['worktree'], root)}")
            print(_c("d", f"  next: agentic deliver schedule {epic['epic_id'][:10]}"))
            return 0
        if args.deliver_cmd == "status":
            epics = [_find_epic(root, args.epic_id)] if args.epic_id else deliver.list_epics(root)
            epics = [e for e in epics if e]
            if not epics:
                print(_c("d", "no epics"))
                return 0
            for e in epics:
                print(_c("b", e["epic_id"][:10]) + _c("d", f"  base {e['base_branch']} · {len(e['items'])} items"))
                for it in e["items"]:
                    r = run.load(root, it["run_id"])
                    state = "merged" if it["merged"] else (r["status"] if r else "?")
                    print(f"    {it['run_id'][:10]}  {state:<14} {(r['phase'] if r else '?'):<10} {it['title']}")
            return 0
        if args.deliver_cmd == "schedule":
            ep = _find_epic(root, args.epic_id)
            if not ep:
                print(_c("r", f"no such epic: {args.epic_id}"))
                return 1
            batches = deliver.schedule(root, ep["epic_id"])
            print(_c("g", f"{len(batches)} batch(es) — items within a batch can run in parallel:"))
            for i, b in enumerate(batches, 1):
                print(f"  batch {i}: " + ", ".join(it["title"] for it in b))
            return 0
        if args.deliver_cmd == "merge":
            res = deliver.merge(root, args.run_id)
            if res.get("ok"):
                print(_c("g", f"✓ merged {res['branch']} → {res['base']}") + _c("d", "  (worktree + branch removed)"))
                return 0
            print(_c("r", "✗ " + res.get("reason", "merge failed")))
            return 2
    except (RuntimeError, ValueError) as e:
        print(_c("r", "✗ " + str(e)))
        return 1
    return 1


def build_parser():
    p = argparse.ArgumentParser(prog="agentic", description="A supervisory framework for agentic development.")
    p.add_argument("-V", "--version", action="version", version=f"agentic {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="scaffold .agentic/bundle.yaml")
    pi.add_argument("--name")
    pi.add_argument("--force", action="store_true")
    pi.set_defaults(func=cmd_init)

    pp = sub.add_parser("project", help="compile bundle into .claude/ + AGENTS.md")
    pp.set_defaults(func=cmd_project)

    pg = sub.add_parser("gate", help="(hook) supervise a tool call from stdin JSON")
    pg.set_defaults(func=cmd_gate)

    pd = sub.add_parser("doctor", help="check bundle, drift, and ledger integrity")
    pd.set_defaults(func=cmd_doctor)

    pl = sub.add_parser("ledger", help="show the provenance ledger")
    pl.add_argument("--run", help="filter by run_id")
    pl.add_argument("--follow", "-f", action="store_true", help="live tail as events arrive")
    pl.set_defaults(func=cmd_ledger)

    pt = sub.add_parser("trace", help="show one run's events")
    pt.add_argument("run_id")
    pt.set_defaults(func=cmd_trace)

    po = sub.add_parser("observe", help="ingest git history into the ledger")
    po.add_argument("--since", default="30 days ago")
    po.set_defaults(func=cmd_observe)

    pa = sub.add_parser("add", help="add a persona/pack from a git source (extends)")
    pa.add_argument("source", help="git::<repo>//<subpath>[@<ref>]")
    pa.set_defaults(func=cmd_add)

    pk = sub.add_parser("lock", help="resolve extends: sources and pin commit shas")
    pk.add_argument("--update", action="store_true", help="re-resolve refs to latest")
    pk.set_defaults(func=cmd_lock)

    prn = sub.add_parser("run", help="drive a unit of work through the lifecycle (gate-enforced)")
    rns = prn.add_subparsers(dest="run_cmd", required=True)
    r_s = rns.add_parser("start", help="start a run")
    r_s.add_argument("title")
    rns.add_parser("list", help="list runs")
    r_st = rns.add_parser("status", help="show one run")
    r_st.add_argument("run_id")
    r_a = rns.add_parser("artifact", help="record a gate artifact for a run")
    r_a.add_argument("run_id")
    r_a.add_argument("name")
    r_a.add_argument("--ref")
    r_av = rns.add_parser("advance", help="advance to the next phase (blocked until the gate is satisfied)")
    r_av.add_argument("run_id")
    prn.set_defaults(func=cmd_run)

    ppl = sub.add_parser("plan", help="scaffold + record the plan note (Definition of Ready)")
    ppl.add_argument("run_id")
    ppl.set_defaults(func=cmd_plan)

    pst = sub.add_parser("status", help="overview: bundle, runs, relays, ledger")
    pst.set_defaults(func=cmd_status)

    pmc = sub.add_parser("mcp", help="run the MCP server (stdio) so agents can call agentic")
    pmc.set_defaults(func=cmd_mcp)

    pdl = sub.add_parser("deliver", help="drive an epic: many items in isolated git worktrees, collision-aware")
    dls = pdl.add_subparsers(dest="deliver_cmd", required=True)
    d_s = dls.add_parser("start", help="start an epic from item titles")
    d_s.add_argument("titles", nargs="+")
    d_sc = dls.add_parser("schedule", help="show parallel/serial batches (collision-aware)")
    d_sc.add_argument("epic_id")
    d_st = dls.add_parser("status", help="show epics and item progress")
    d_st.add_argument("epic_id", nargs="?")
    d_m = dls.add_parser("merge", help="merge a completed item back to base")
    d_m.add_argument("run_id")
    pdl.set_defaults(func=cmd_deliver)

    pr = sub.add_parser("relay", help="human-in-the-loop queue")
    rsub = pr.add_subparsers(dest="relay_cmd", required=True)
    rsub.add_parser("list")
    rr = rsub.add_parser("resolve")
    rr.add_argument("relay_id")
    rr.add_argument("--approve", action="store_true")
    rr.add_argument("--edit", action="store_true")
    rr.add_argument("--reject", action="store_true")
    rr.add_argument("--approver")
    rr.add_argument("--reason")
    pr.set_defaults(func=cmd_relay)

    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    return args.func(args)
