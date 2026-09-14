#!/usr/bin/env python3
"""
fix_page_paths.py

Matches loose .mdx files (e.g. untitled-page-14.mdx) to the paths declared
in docs.json's navigation, based on each file's frontmatter title, then
moves the files into place so URLs actually resolve.

USAGE:
  1. Put this script in the ROOT of your repo (same folder as docs.json).
  2. Dry run first (just prints what it WOULD do, changes nothing):
       python3 fix_page_paths.py
  3. If the mapping looks right, actually apply it:
       python3 fix_page_paths.py --apply
  4. Review with `git status` / `git diff --stat`, then commit and push as usual.

Nothing is deleted. Files that are already correctly placed, or that the
script can't confidently match, are left untouched and listed separately.
"""

import json
import os
import re
import sys
import shutil

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS_JSON = os.path.join(REPO_ROOT, "docs.json")
APPLY = "--apply" in sys.argv


def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def collect_nav_paths(node, acc):
    """Recursively walk docs.json and collect every string found under a
    'pages' key -- these are the declared page paths."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "pages" and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        acc.add(item)
                    else:
                        collect_nav_paths(item, acc)
            else:
                collect_nav_paths(value, acc)
    elif isinstance(node, list):
        for item in node:
            collect_nav_paths(item, acc)


def read_frontmatter_title(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    frontmatter = content[3:end]
    match = re.search(r'^(?:title|sidebarTitle)\s*:\s*["\']?(.+?)["\']?\s*$',
                       frontmatter, re.MULTILINE)
    return match.group(1) if match else None


def find_all_mdx(root):
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules")]
        for fn in filenames:
            if fn.endswith(".mdx"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                rel_no_ext = rel[:-4]  # strip .mdx
                result.append((rel_no_ext.replace(os.sep, "/"), full))
    return result


def main():
    if not os.path.exists(DOCS_JSON):
        print(f"Could not find docs.json at {DOCS_JSON}")
        print("Put this script in the same folder as docs.json and rerun.")
        sys.exit(1)

    with open(DOCS_JSON, "r", encoding="utf-8") as f:
        docs_config = json.load(f)

    nav_paths = set()
    collect_nav_paths(docs_config, nav_paths)

    mdx_files = find_all_mdx(REPO_ROOT)
    existing_paths = {p for p, _ in mdx_files}

    already_correct = nav_paths & existing_paths
    missing_nav_paths = nav_paths - existing_paths

    # Only consider "loose" files as move candidates: files whose current
    # path isn't already a declared nav path (so we don't touch anything
    # that's already correctly wired up, e.g. the intentional
    # untitled-page-2..24 entries under Data and Discovery).
    candidate_files = [(p, full) for p, full in mdx_files if p not in nav_paths]

    matches = []       # (current_rel_path, target_nav_path, full_source_path)
    unmatched_files = []
    used_targets = set()

    for rel_path, full_path in candidate_files:
        title = read_frontmatter_title(full_path)
        if not title:
            unmatched_files.append((rel_path, "no title in frontmatter"))
            continue
        title_slug = slugify(title)

        found_target = None
        for nav_path in missing_nav_paths:
            if nav_path in used_targets:
                continue
            last_segment = nav_path.rstrip("/").split("/")[-1]
            if slugify(last_segment) == title_slug:
                found_target = nav_path
                break

        if found_target:
            matches.append((rel_path, found_target, full_path))
            used_targets.add(found_target)
        else:
            unmatched_files.append((rel_path, f"title '{title}' didn't match any missing nav path"))

    still_missing = missing_nav_paths - used_targets

    # --- Report ---
    print("=" * 70)
    print(f"Nav paths declared in docs.json : {len(nav_paths)}")
    print(f"Already correctly placed        : {len(already_correct)}")
    print(f"Loose/misnamed files found      : {len(candidate_files)}")
    print("=" * 70)

    if matches:
        print("\nMATCHED (will be moved):\n")
        for rel_path, target, _ in matches:
            print(f"  {rel_path}.mdx  ->  {target}.mdx")

    if unmatched_files:
        print("\nCOULD NOT MATCH (left alone -- check these manually):\n")
        for rel_path, reason in unmatched_files:
            print(f"  {rel_path}.mdx  ({reason})")

    if still_missing:
        print("\nNAV PATHS WITH NO FILE FOUND AT ALL (still needs a page created):\n")
        for p in sorted(still_missing):
            print(f"  {p}.mdx")

    if not matches:
        print("\nNothing to move.")
        return

    if not APPLY:
        print(f"\nDry run only -- no files were changed.")
        print(f"Re-run with --apply to actually move these {len(matches)} file(s).")
        return

    print(f"\nApplying {len(matches)} move(s)...")
    for rel_path, target, full_path in matches:
        target_full = os.path.join(REPO_ROOT, target + ".mdx")
        os.makedirs(os.path.dirname(target_full), exist_ok=True)
        shutil.move(full_path, target_full)
        print(f"  moved: {rel_path}.mdx -> {target}.mdx")

    print("\nDone. Now run:")
    print("  git add -A")
    print('  git commit -m "Rename pages to match docs.json navigation"')
    print("  git push")


if __name__ == "__main__":
    main()