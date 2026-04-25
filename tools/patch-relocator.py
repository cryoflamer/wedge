#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys

ERR_NOACTION = 2
ERR_UNRESOLVED = 3

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def inside_repo():
    rc, _, _ = run(["git","rev-parse","--is-inside-work-tree"])
    return rc == 0

def list_candidates(include_untracked=False):
    rc, out, _ = run(["git","ls-files","--full-name","-z"])
    tracked = out.split("\x00") if out else []
    cand = [p for p in tracked if p]
    if include_untracked:
        rc, out, _ = run(["git","ls-files","-o","--exclude-standard","--full-name","-z"])
        cand += [p for p in (out.split("\x00") if out else []) if p]
    return cand

MISS_PATTERNS = [
    re.compile(r"error: path '([^']+)' does not exist", re.I),
    re.compile(r"error: (.+?): No such file or directory", re.I),
    re.compile(r"fatal: unable to read \w+ '([^']+)'", re.I),
]

def parse_missing(stderr_text):
    missing = set()
    for line in stderr_text.splitlines():
        for pat in MISS_PATTERNS:
            m = pat.search(line)
            if m:
                missing.add(m.group(1))
    return sorted(missing)

def extract_patch_paths(patch_text):
    files = []
    for m in re.finditer(r"^diff --git a/(.+?) b/(.+)$", patch_text, re.M):
        a, b = m.group(1), m.group(2)
        files.append((a, b))
    return files

def rewrite_patch(patch_text, mapping):
    def repl_diff(m):
        a, b = m.group(1), m.group(2)
        return f"diff --git a/{mapping.get(a,a)} b/{mapping.get(b,b)}"
    def repl_from(m):
        p = m.group(1)
        return f"rename from {mapping.get(p,p)}"
    def repl_to(m):
        p = m.group(1)
        return f"rename to {mapping.get(p,p)}"
    def repl_minus(m):
        p = m.group(1)
        return f"--- a/{mapping.get(p,p)}"
    def repl_plus(m):
        p = m.group(1)
        return f"+++ b/{mapping.get(p,p)}"
    txt = patch_text
    txt = re.sub(r"^diff --git a/(.+?) b/(.+)$", repl_diff, txt, flags=re.M)
    txt = re.sub(r"^rename from (.+)$", repl_from, txt, flags=re.M)
    txt = re.sub(r"^rename to (.+)$", repl_to, txt, flags=re.M)
    txt = re.sub(r"^--- a/(.+)$", repl_minus, txt, flags=re.M)
    txt = re.sub(r"^\+\+\+ b/(.+)$", repl_plus, txt, flags=re.M)
    return txt

def main():
    ap = argparse.ArgumentParser(description="Patch preflight path remapper")
    ap.add_argument("patch")
    ap.add_argument("-y", action="store_true", help="autoselect when only one candidate exists (otherwise interactive)")
    ap.add_argument("--include-untracked", action="store_true", help="also search among untracked files")
    ap.add_argument("--allow-touch-scripts", action="store_true", help="allow remapping into tools/** (blocked by default)")
    args = ap.parse_args()

    if not inside_repo():
        print("Not inside a git repo.", file=sys.stderr); return 1
    patch_path = args.patch
    if not os.path.isfile(patch_path):
        print(f"No such patch: {patch_path}", file=sys.stderr); return 1

    rc, _, _ = run(["git","apply","--check",patch_path])
    if rc == 0:
        print(patch_path)
        return ERR_NOACTION

    rc, _, err = run(["git","apply","--check","-v",patch_path])
    missing = parse_missing(err)

    with open(patch_path,encoding="utf-8",errors="replace") as f:
        txt = f.read()
    pairs = extract_patch_paths(txt)
    paths_in_patch = sorted(set([a for a,b in pairs] + [b for a,b in pairs]))

    cand_list = list_candidates(include_untracked=args.include_untracked)
    all_set = set(cand_list)
    really_missing = [p for p in paths_in_patch if p not in all_set]
    targets = sorted(set(missing + really_missing))

    if not targets:
        return ERR_UNRESOLVED

    mapping = {}
    by_base = {}
    for p in cand_list:
        by_base.setdefault(os.path.basename(p), []).append(p)

    for old in targets:
        base = os.path.basename(old)
        cands = by_base.get(base, [])
        if not args.allow_touch_scripts:
            cands = [c for c in cands if not c.startswith("tools/")]
        chosen = None
        if len(cands) == 1 and args.y:
            chosen = cands[0]
            print(f"[relocator] auto: {old} -> {chosen}", file=sys.stderr)
        elif len(cands) >= 1 and args.y:
            chosen = cands[0]
            print(f"[relocator] multiple candidates for {old}, picking first due to -y: {chosen}", file=sys.stderr)
        elif len(cands) >= 1:
            print(f"[relocator] candidates for {old}:", file=sys.stderr)
            for i,p in enumerate(cands,1):
                print(f"  [{i}] {p}", file=sys.stderr)
            ans = input(f"Choose 1-{len(cands)} or 's' to skip: ").strip()
            if ans and ans[0].lower()!='s' and ans.isdigit():
                i = int(ans)
                if 1 <= i <= len(cands):
                    chosen = cands[i-1]
        if chosen:
            mapping[old] = chosen

    if not mapping:
        return ERR_UNRESOLVED

    new_txt = rewrite_patch(txt, mapping)
    new_path = patch_path + ".relocated.patch"
    with open(new_path,"w",encoding="utf-8") as f:
        f.write(new_txt)

    rc2, _, err2 = run(["git","apply","--check",new_path])
    if rc2 != 0:
        print("[relocator] relocated patch still fails --check", file=sys.stderr)
        print(err2, file=sys.stderr)
        return ERR_UNRESOLVED

    print(new_path)
    return 0

if __name__=="__main__":
    sys.exit(main())
