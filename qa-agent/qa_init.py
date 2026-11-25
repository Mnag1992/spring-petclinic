#!/usr/bin/env python3
"""
qa_init.py - draft the post-merge QA agent setup for a repository (no AI, standard library only).

    python qa_init.py [repo_dir] [--force] [--check]

Scans the repository and writes
    qa-agent/qa-agent.config.json            the agent's project settings
    .github/workflows/post-merge-qa.yml      the GitHub Actions workflow
then prints a plain-language review sheet: what was found (sure) and what it only guessed (check).
Nothing is overwritten unless --force is given (the drafts get a .draft suffix instead).
--check prints the review sheet only and writes nothing.
"""
import fnmatch
import json
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "target", "build", "dist", "out", "bin", "obj", ".idea", ".vscode", ".venv", "venv",
             "__pycache__", ".gradle", ".mvn", "playwright-report", "test-results", "coverage", ".next", "qa-agent",
             "qa-results", "qa-quarantine", ".github"}
SHARED_WORDS = {"model", "models", "common", "shared", "system", "core", "util", "utils", "config", "infrastructure",
                "base", "domain", "service-defaults", "servicedefaults", "lib", "app", "root"}
UI_EXTS = [".html", ".razor", ".cshtml", ".vue", ".tsx", ".jsx", ".svelte", ".jsp", ".ftl"]
CODE_EXTS = {".java": "java", ".kt": "java", ".cs": "dotnet", ".py": "python", ".ts": "node", ".tsx": "node",
             ".js": "node", ".jsx": "node", ".vue": "node", ".razor": "dotnet"}

NON_COMPONENT = {"test", "tests", "resources", "static", "assets", "public", "__tests__", "e2e"}

SURE, CHECK = "✅", "❓"


# --------------------------------------------------------------------------- #
def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(files):
            p = os.path.join(d, f)
            yield os.path.relpath(p, root).replace("\\", "/")


def read(root, rel, limit=200000):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def words(name):
    """'FindOwners' / 'find_owners' / 'find-owners' -> ['find', 'owners']"""
    name = re.sub(r"\.(spec|test|cy|feature|steps?)\b", "", name)
    name = os.path.splitext(name)[0]
    parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", name)
    return [p.lower() for p in parts]


def stem(w):
    w = w.lower()
    for suf in ("ies", "es", "s"):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


# --------------------------------------------------------------------------- #
class Finding:
    def __init__(self):
        self.rows = []  # (mark, topic, text)

    def add(self, mark, topic, text):
        self.rows.append((mark, topic, text))


def detect_runner(root, files, F):
    names = {os.path.basename(f) for f in files}
    pkg = read(root, "package.json") if "package.json" in files else ""
    pom = read(root, "pom.xml") + read(root, "build.gradle") + read(root, "build.gradle.kts")
    features = [f for f in files if f.endswith(".feature")]
    if any(re.match(r"playwright\.config\.(ts|js|mjs)$", n) for n in names):
        F.add(SURE, "Test framework", "Playwright (playwright.config found)")
        return "playwright"
    if any(re.match(r"cypress\.config\.(ts|js|mjs)$", n) for n in names):
        F.add(SURE, "Test framework", "Cypress (cypress.config found)")
        return "cypress"
    if features and re.search(r"cucumber", pom, re.I):
        F.add(SURE, "Test framework", "Cucumber with Java (cucumber in the Maven/Gradle file and .feature files found)")
        return "cucumber-java"
    if "vitest" in pkg:
        F.add(SURE, "Test framework", "Vitest (vitest in package.json)")
        return "vitest"
    if "jest" in pkg:
        F.add(SURE, "Test framework", "Jest (jest in package.json)")
        return "jest"
    if "pytest.ini" in names or "conftest.py" in names or any(f.startswith("test_") and f.endswith(".py") for f in names):
        F.add(SURE, "Test framework", "pytest")
        return "pytest"
    F.add(CHECK, "Test framework", "none recognised - set runner.preset by hand")
    return "playwright"


SPEC_GLOBS = {"playwright": ["*.spec.ts", "*.spec.js"], "cypress": ["*.cy.ts", "*.cy.js"], "jest": ["*.test.ts", "*.test.js", "*.spec.ts"],
              "vitest": ["*.test.ts", "*.test.js", "*.spec.ts"], "pytest": ["test_*.py", "*_test.py"], "cucumber-java": ["*.feature"]}


def detect_tests(files, preset, F):
    globs = SPEC_GLOBS.get(preset, ["*.spec.ts"])
    specs = [f for f in files if any(fnmatch.fnmatch(os.path.basename(f), g) for g in globs)]
    if not specs:
        F.add(CHECK, "Test folder", "no test files found")
        return "", []
    dirs = {}
    for s in specs:
        dirs.setdefault(os.path.dirname(s), []).append(s)
    top = os.path.commonpath([os.path.dirname(s) or "." for s in specs]) if len(dirs) > 1 else next(iter(dirs))
    top = "" if top == "." else top.replace("\\", "/")
    F.add(SURE, "Test folder", f"{top or '.'} ({len(specs)} test files)")
    return top, specs


def detect_source(root, files, tests_dir, F):
    """Source dir = the folder with the most non-test code; extensions from the dominant language."""
    counts, exts = {}, {}
    for f in files:
        ext = os.path.splitext(f)[1]
        if ext not in CODE_EXTS or (tests_dir and f.startswith(tests_dir + "/")) or "/test/" in f or "/tests/" in f:
            continue
        top = f.split("/")[0]
        counts[top] = counts.get(top, 0) + 1
        exts[ext] = exts.get(ext, 0) + 1
    if not counts:
        return "src", [".py"], F.add(CHECK, "Source folder", "no application code found") or "other"
    src = max(counts, key=counts.get)
    lang_votes = {}
    for e, n in exts.items():
        lang_votes[CODE_EXTS[e]] = lang_votes.get(CODE_EXTS[e], 0) + n
    lang = max(lang_votes, key=lang_votes.get)
    keep = [e for e in sorted(exts) if CODE_EXTS[e] == lang]
    if lang == "java":
        keep += [".html", ".properties"]
    if lang == "dotnet":
        keep = sorted(set(keep) | {".razor"})
    F.add(SURE, "Source folder", f"{src}/ ({lang}); file types {', '.join(keep)}")
    return src, keep, lang


def detect_port(root, files, preset, lang, F):
    pat = [
        ("application.properties", r"server\.port\s*=\s*(\d+)"), ("application.yml", r"port:\s*(\d+)"),
        ("playwright.config.ts", r"localhost:(\d+)"), ("playwright.config.js", r"localhost:(\d+)"),
        ("cypress.config.ts", r"localhost:(\d+)"), ("cypress.config.js", r"localhost:(\d+)"),
        ("package.json", r"(?:--port[= ]|PORT=)(\d+)"), ("launchSettings.json", r"localhost:(\d+)"),
    ]
    for f in files:
        for name, rx in pat:
            if os.path.basename(f) == name:
                m = re.search(rx, read(root, f))
                if m:
                    F.add(SURE, "App port", f"{m.group(1)} (from {f})")
                    return int(m.group(1))
    default = {"java": 8080, "node": 3000, "dotnet": 5000, "python": 8000}.get(lang, 8080)
    F.add(CHECK, "App port", f"{default} assumed - no port setting found, confirm it")
    return default


def top_dirs_with_code(root, files, src, exts):
    """Components = the sub-folders under the first folder level that splits into 2+ areas."""
    base = src
    while True:
        subs = {}
        direct = 0
        for f in files:
            if not f.startswith(base + "/") or os.path.splitext(f)[1] not in exts:
                continue
            rest = f[len(base) + 1:].split("/")
            if len(rest) > 1 and rest[0].lower() in NON_COMPONENT:
                continue
            if len(rest) == 1:
                direct += 1
            else:
                subs.setdefault(rest[0], []).append(f)
        total = sum(len(v) for v in subs.values()) + direct
        big = max(subs, key=lambda k: len(subs[k])) if subs else None
        # one folder holding almost all the code (src/main -> java) is a wrapper: step into it
        if big and (len(subs) == 1 or len(subs[big]) / total >= 0.8) and direct == 0:
            base = base + "/" + big
            continue
        return base, sorted(subs), direct


def detect_components(root, files, src, exts, F):
    base, subs, direct = top_dirs_with_code(root, files, src, exts)
    skip = {"test", "tests", "resources", "static", "assets", "public"}
    subs = [s for s in subs if s.lower() not in skip]
    comps = {s: [f"{base}/{s}"] for s in subs}
    if direct:
        comps["app"] = [f"{base}/<root files>"]
    if not comps:
        F.add(CHECK, "Components", "no sub-folders found - everything is treated as one component")
        return {}, base
    F.add(SURE if len(comps) > 1 else CHECK, "Components (code areas)", ", ".join(comps) + f"  (folders under {base}/)")
    return comps, base


def attach_ui_dirs(files, comps, F):
    """Template / page folders: attach to the component whose name matches (owner <-> owners); list the rest."""
    ui_dirs = {}
    for f in files:
        if os.path.splitext(f)[1] in UI_EXTS and "/test" not in f:
            ui_dirs.setdefault(os.path.dirname(f), []).append(f)
    if not ui_dirs:
        return [], []
    root_ui = max(ui_dirs, key=lambda d: len(ui_dirs[d]))
    # the common parent of the folders that hold most markup, e.g. src/main/resources/templates
    parent = os.path.commonpath(list(ui_dirs)) if len(ui_dirs) > 1 else root_ui
    parent = parent.replace("\\", "/")
    if parent in ("", "."):
        parent = root_ui
    exts = sorted({os.path.splitext(f)[1] for fs in ui_dirs.values() for f in fs})
    unmatched = []
    for d in sorted(ui_dirs):
        leaf = d.split("/")[-1]
        hit = next((c for c in comps if stem(c) == stem(leaf)), None)
        if hit and d != parent:
            comps[hit].append(d)
        elif d != parent:
            unmatched.append(d)
    if unmatched:
        F.add(CHECK, "Page folders not matched to a component",
              ", ".join(u[len(parent) + 1:] if u.startswith(parent + "/") else u for u in unmatched) +
              f" (under {parent}/) - say which component owns them, or they count as shared")
    return [parent], exts


def detect_specs_map(root, specs, comps, tests_dir, F):
    """Which tests does each component affect? Names first, then page paths that appear in both code and tests."""
    spec_names = []
    for s in specs:
        n = os.path.basename(s)
        spec_names.append(re.sub(r"(\.(spec|test|cy))?\.(ts|js|py|feature)$", "", n))
    comp_words = {c: stem(re.sub(r"[^a-z0-9]", "", c.lower())) for c in comps}
    mapping = {c: [] for c in comps}
    unsure_specs, matched_specs = [], set()
    for sn, sp in zip(spec_names, specs):
        toks = {stem(w) for w in words(sn)}
        hit = False
        for c, w in comp_words.items():
            if c.lower() in SHARED_WORDS:
                continue
            if w in toks or any(w and (t.startswith(w) or w.startswith(t)) and len(t) > 3 for t in toks):
                mapping[c].append(sn)
                hit = True
        if hit:
            matched_specs.add(sn)
    # page paths shared by a test and a component's code
    for sn, sp in zip(spec_names, specs):
        paths = set(re.findall(r"""['"](/[a-zA-Z0-9_\-/]{2,})['"]""", read(root, sp)))
        for c, dirs in comps.items():
            if c.lower() in SHARED_WORDS or sn in mapping[c]:
                continue
            if paths and any(p in read_all(root, d) for p in paths for d in dirs[:1]):
                mapping[c].append(sn)
                matched_specs.add(sn)
    shared = [c for c in comps if c.lower() in SHARED_WORDS]
    for c in shared:
        mapping[c] = list(spec_names)  # shared code can affect every journey
    for sn in spec_names:
        if sn not in matched_specs:
            unsure_specs.append(sn)
    if not mapping:
        return mapping, spec_names, []
    lines = [f"{c} -> {', '.join(v) or '(no tests)'}" for c, v in mapping.items()]
    F.add(CHECK, "Which tests each area affects", "\n        ".join(lines))
    if unsure_specs:
        F.add(CHECK, "Tests that matched no area", ", ".join(unsure_specs) +
              " - they run only for shared areas (" + (", ".join(shared) or "none") + "); say which area they belong to")
    nomatch = [c for c in comps if not mapping[c] and c.lower() not in SHARED_WORDS]
    if nomatch:
        F.add(CHECK, "Areas with no test", ", ".join(nomatch) + " - fine if nothing covers them yet (the agent will write tests)")
    return mapping, spec_names, unsure_specs


_CACHE = {}


def read_all(root, d):
    if d in _CACHE:
        return _CACHE[d]
    out = []
    base = os.path.join(root, d)
    for dp, dirs, fs in os.walk(base):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in fs:
            if os.path.splitext(f)[1] in CODE_EXTS or os.path.splitext(f)[1] in UI_EXTS:
                try:
                    with open(os.path.join(dp, f), encoding="utf-8", errors="replace") as fh:
                        out.append(fh.read(40000))
                except OSError:
                    pass
    _CACHE[d] = "\n".join(out)
    return _CACHE[d]


def detect_helpers(root, files, tests_dir, specs, preset, F):
    ext = {"cucumber-java": [".java"], "pytest": [".py"]}.get(preset, [".ts", ".js"])
    spec_set = set(specs)
    scope = ["src/test", "test", "tests", "e2e", "cypress"] + ([tests_dir] if tests_dir else [])
    helpers = []
    for f in files:
        if f in spec_set or os.path.splitext(f)[1] not in ext:
            continue
        if not any(f.startswith(s + "/") for s in scope) and not (tests_dir and f.startswith(tests_dir)):
            continue
        txt = read(root, f, 6000)
        if preset == "cucumber-java" and not re.search(r"@(Given|When|Then|And)\b", txt):
            continue
        if re.search(r"(config|setup|runner)", os.path.basename(f), re.I) and preset != "cucumber-java":
            continue
        helpers.append(f)
    helpers = helpers[:5]
    if helpers:
        F.add(SURE, "Helper files the AI may reuse", ", ".join(helpers))
    return helpers


def detect_support(files, preset):
    if preset == "cucumber-java":
        d = "src/test/java"
        return [d] if any(f.startswith(d + "/") for f in files) else []
    return []


def detect_seed_data(files, F):
    out = []
    cands = [f for f in files if os.path.basename(f).lower() in ("data.sql", "import.sql")
             or re.match(r"(seed|fixtures?).*\.(json|sql)$", os.path.basename(f).lower())]
    cands.sort(key=lambda f: (0 if re.search(r"hsqldb|h2", f) else 1, f))  # the embedded database starts with the app
    for f in cands[:1]:
        b = os.path.basename(f).lower()
        if True:
            if b.endswith(".sql"):
                out.append({"file": f, "format": "text", "grep": "^INSERT INTO", "title": "Seeded data (SQL inserts)",
                            "note": "the ONLY data that exists at start-up; names, cities and numbers are exact", "max_chars": 6000})
            else:
                out.append({"file": f, "title": "Seeded data", "note": "the ONLY data that exists at start-up"})
    if out:
        F.add(SURE, "Seeded test data", ", ".join(o["file"] for o in out))
    else:
        F.add(CHECK, "Seeded test data", "none found - if the app starts with data, name that file under test_data")
    return out


def detect_global_files(files, F):
    names = ["pom.xml", "build.gradle", "build.gradle.kts", "package.json", "package-lock.json", "pyproject.toml",
             "requirements.txt", "playwright.config.ts", "cypress.config.ts", "Directory.Build.props", "global.json",
             "application.properties", "application.yml"]
    found = [f for f in files if os.path.basename(f) in names and f.count("/") <= 3 and "/test/" not in f]
    return sorted(found)[:10]


def detect_login(files, root, preset, F):
    setup = next((f for f in files if re.search(r"(login|auth)[._-]?setup\.(ts|js)$", f)), "")
    text = " ".join(read(root, f, 4000) for f in files if f.endswith(("Controller.java", "security.py")))[:20000]
    has_login = bool(setup) or re.search(r"(?i)(WebSecurity|spring-security|passport|login)", read(root, "pom.xml") + text)
    if setup:
        F.add(SURE, "Login", f"login setup file found: {setup}")
        return setup, False
    if has_login:
        F.add(CHECK, "Login", "the code mentions login - if tests need a logged-in user, fill login_setup and auth_specs")
        return "", False
    F.add(SURE, "Login", "no login found - tests run anonymously")
    return "", True


def extract_ui_facts(root, files, ui_parent, F):
    """Headings, form ids and field names from the page templates -> app_rules for the AI."""
    heads, forms, fields, links = {}, set(), set(), set()
    pages = []
    for f in files:
        if not any(f.startswith(p + "/") for p in ui_parent) or os.path.splitext(f)[1] not in UI_EXTS:
            continue
        t = read(root, f, 30000)
        for m in re.finditer(r"<h([12])[^>]*>\s*([^<{$]{2,40}?)\s*</h\1>", t):
            heads.setdefault(m.group(2).strip(), f)
        forms |= set(re.findall(r"<form[^>]*\bid=\"([^\"]+)\"", t))
        fields |= set(re.findall(r"<input[^>]*\bname=\"([^\"]+)\"", t))
        fields |= {m for m in re.findall(r"'[A-Za-z ]+',\s*'([a-z][A-Za-z]+)',\s*'(?:text|number|email|password)'", t)}
        links |= set(re.findall(r"<a[^>]*>\s*([A-Z][A-Za-z ]{2,30}?)\s*</a>", t))
        pages.append(f)
    bits = []
    if heads:
        bits.append("Page headings: " + ", ".join(f"'{h}'" for h in list(heads)[:12]) + ".")
    if forms:
        bits.append("Form ids: " + ", ".join(f"'{x}'" for x in sorted(forms)[:8]) + ".")
    if fields:
        bits.append("Input fields are named exactly: " + ", ".join(f"'{x}'" for x in sorted(fields)[:16]) +
                    " - never use the visible labels as names.")
    if links:
        bits.append("Link texts: " + ", ".join(f"'{x}'" for x in sorted(links)[:10]) + ".")
    if bits:
        F.add(SURE, "Pages, forms and fields (for the AI)", f"{len(pages)} page files read: headings, form ids, field names")
    return " ".join(bits)


def readme_summary(root, files):
    for f in files:
        if os.path.basename(f).lower() in ("readme.md", "readme"):
            text = read(root, f, 6000)
            paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 60 and not p.strip().startswith(("#", "!", "[", "<", "```"))]
            if paras:
                return " ".join(paras[0].split())[:400]
    return ""


# --------------------------------------------------------------------------- #
PRESET_RULES = {
    "cucumber-java": {
        "helpers_rules": "reuse ONLY the steps defined in the step files shown in the framework section; copy their wording exactly.",
        "extra": "Filling a field ADDS to the text already in it: on an edit form first clear the field, then fill it. "
                 "On a page with a validation error, entered values are inside input boxes, not page text.",
        "example_step": "open the page, fill a field and check the result", "example_page": "/",
        "e2e_dir_default": "src/test/resources/scenarios", "gen": "generated",
    },
    "playwright": {"helpers_rules": "reuse the existing helpers instead of re-implementing them; imports are relative to the generated folder.",
                   "extra": "", "example_step": "open the page, click, check the result", "example_page": "/", "gen": "generated"},
}


def build_config(root, files, F):
    preset = detect_runner(root, files, F)
    tests_dir, specs = detect_tests(files, preset, F)
    src, exts, lang = detect_source(root, files, tests_dir, F)
    port = detect_port(root, files, preset, lang, F)
    comps, comp_base = detect_components(root, files, src, exts, F)
    ui_parents, ui_exts = attach_ui_dirs(files, comps, F)
    mapping, spec_names, unsure = detect_specs_map(root, specs, comps, tests_dir, F)
    helpers = detect_helpers(root, files, tests_dir, specs, preset, F)
    data = detect_seed_data(files, F)
    login_setup, no_login = detect_login(files, root, preset, F)
    ui_facts = extract_ui_facts(root, files, ui_parents, F)
    desc = readme_summary(root, files)
    rules = PRESET_RULES.get(preset, PRESET_RULES["playwright"])
    gen_dir = (tests_dir + "/" if tests_dir else "") + rules.get("gen", "generated")
    # components for Java-style layouts: real folders
    comp_cfg = {}
    for c, dirs in comps.items():
        real = [d for d in dirs if "<root files>" not in d]
        if not real and comp_base:
            real = [f for f in files if f.startswith(comp_base + "/") and f.count("/") == comp_base.count("/") + 1
                    and os.path.splitext(f)[1] in exts]
        comp_cfg[c] = real
    cfg = {
        "_comment": "Draft written by qa_init.py - review the lines marked in the review sheet, then delete this comment.",
        "project_name": os.path.basename(os.path.abspath(root)),
        "app_port": port,
        "keep_env": [],
        "runner": {"preset": preset},
        "project_description": desc or "FILL IN: one or two sentences on what the application does",
        "suite_description": f"{preset} tests in {tests_dir or 'the test folder'} run against the running application on port {port}.",
        "src_dir": src, "e2e_dir": tests_dir, "generated_dir": gen_dir,
        "login_setup": login_setup, "no_login": no_login,
        "default_owner": next((c for c in comps if c.lower() not in SHARED_WORDS), "app"),
        "source_extensions": exts, "global_files": detect_global_files(files, F),
        "support_dirs": detect_support(files, preset),
        "components": comp_cfg,
        "auth_specs": [], "all_specs": [], "default_specs": [],
        "spec_map": mapping,
        "helper_files": helpers,
        "ui_markup": {"dirs": ui_parents, "extensions": ui_exts or [".html"], "budget_chars": 40000},
        "test_data": data,
        "prompts_dir": "qa-agent/prompts",
        "prompt_vars": {
            "example_step": rules["example_step"], "example_test_id": (specs[0] if specs else "tests/example"),
            "example_page": rules["example_page"], "example_paths": "'/'",
            "helpers_rules": rules["helpers_rules"],
            "auth_rules": "The application has no login and no stored session." if no_login else
                          "Authentication is handled by the test setup - never log in inside a generated test.",
            "app_rules": (ui_facts + " " + rules["extra"] + " Take element names, labels and headings from the provided markup only. "
                          "Exact validation messages were not detected - use only messages that appear in the markup or test data.").strip(),
        },
    }
    if lang != "java":
        cfg.pop("components")
        cfg.pop("support_dirs")
    if preset != "cucumber-java":
        cfg.pop("no_login", None)
        cfg.pop("default_owner", None)
    F.add(CHECK, "Project description", "taken from the README - check it describes the app" if desc else "FILL IN project_description")
    F.add(CHECK, "Validation messages", "not detectable from code. After the first run, add the exact messages the app shows to prompt_vars.app_rules")
    return cfg, preset, lang


WORKFLOW_HEAD = """name: Post-Merge Autonomous QA Pipeline

on:
  pull_request:
    types: [closed]
    branches: [main]
  workflow_dispatch:
    inputs:
      base:
        description: 'Diff base (commit/ref). The pipeline analyses base..HEAD of main.'
        required: false
        default: 'HEAD~1'
      dry_run:
        description: 'Analysis only (impact analysis, no LLM calls, no test execution)'
        type: boolean
        default: false

concurrency:
  group: post-merge-qa
  cancel-in-progress: false

jobs:
  run-qa-agent:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event.pull_request.merged == true &&
       !startsWith(github.event.pull_request.head.ref, 'qa-agent/'))
    runs-on: ubuntu-latest
    timeout-minutes: 90
    permissions:
      contents: write
      pull-requests: write
      models: read

    steps:
      - name: Checkout merged code
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.merge_commit_sha || github.ref }}
          fetch-depth: 0

      - name: Resolve PR diff range
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          MANUAL_BASE: ${{ inputs.base || 'HEAD~1' }}
        run: |
          if [ -n "$PR_NUMBER" ]; then
            git fetch --no-tags origin "+refs/pull/${PR_NUMBER}/head:refs/remotes/origin/pr-head"
            echo "DIFF_BASE=$(git merge-base "$BASE_SHA" origin/pr-head)" >> "$GITHUB_ENV"
            echo "DIFF_HEAD=origin/pr-head" >> "$GITHUB_ENV"
          else
            echo "DIFF_BASE=$(git rev-parse "$MANUAL_BASE")" >> "$GITHUB_ENV"
            echo "DIFF_HEAD=HEAD" >> "$GITHUB_ENV"
          fi

"""

SETUP = {
    "java": """      - name: Setup Java 17 + Maven cache
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Make the Maven wrapper executable
        run: chmod +x mvnw

""",
    "node": """      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: lts/*

      - name: Install npm dependencies
        run: npm ci

""",
    "dotnet": """      - name: Setup .NET
        uses: actions/setup-dotnet@v4
        with:
          global-json-file: global.json

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: lts/*

      - name: Install npm dependencies
        run: npm ci

""",
    "python": """      - name: Install test dependencies
        run: pip install -r requirements.txt

""",
}

WORKFLOW_TAIL = """      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Execute Multi-Agent Engine & Targeted Tests
        id: agent
        env:
          PYTHONUNBUFFERED: 1
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          LLM_PROVIDERS: github,gemini,anthropic
          QA_DRY_RUN: ${{ inputs.dry_run }}
        run: python post_merge_qa_agent.py

      - name: Upload QA report & test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: qa-report
          path: |
            qa-report.md
            qa-results/
            qa-quarantine/
            @@REPORT_PATHS@@
          if-no-files-found: ignore

      - name: Comment QA report on the merged PR
        if: always() && github.event_name == 'pull_request'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          [ -f qa-report.md ] || exit 0
          head -c 60000 qa-report.md > qa-comment.md
          echo -e "\\n\\n[Full run](${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }})" >> qa-comment.md
          gh pr comment ${{ github.event.pull_request.number }} --body-file qa-comment.md

      - name: Publish new automation
        if: always() && steps.agent.outcome == 'success'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          COMMIT_MODE: ${{ vars.QA_COMMIT_MODE || 'pr' }}
          QA_GENERATED_DIR: @@GEN_DIR@@
          SOURCE_PR: ${{ github.event.pull_request.number }}
        run: |
          git config --global user.name "AI-QA-Agent[bot]"
          git config --global user.email "ai-qa-agent@users.noreply.github.com"
          [ -d "$QA_GENERATED_DIR" ] && git add "$QA_GENERATED_DIR"
          [ -d qa-agent/prompts ] && git add qa-agent/prompts
          if git diff --staged --quiet; then
            echo "No new tests generated."
            exit 0
          fi
          if [ "$COMMIT_MODE" = "main" ]; then
            git commit -m "chore(qa): automate missing QA scenarios [skip ci]"
            git pull --rebase origin main
            git push origin HEAD:main
          else
            BRANCH="qa-agent/tests-${GITHUB_RUN_ID}"
            git checkout -b "$BRANCH"
            git commit -m "chore(qa): automate missing QA scenarios"
            git push origin "$BRANCH"
            gh pr create --base main --head "$BRANCH" \\
              --title "QA agent: automate missing scenarios${SOURCE_PR:+ (from #$SOURCE_PR)}" \\
              --body "Tests generated and validated by the post-merge QA agent${SOURCE_PR:+ for #$SOURCE_PR}. Please review before merging. Run: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}" \\
              || echo "::warning::Could not open a PR automatically (enable 'Allow GitHub Actions to create and approve pull requests'). The tests are on branch $BRANCH."
          fi

      - name: Open draft PR for held-back automation
        if: always() && hashFiles('qa-quarantine/@@SPEC_GLOB@@') != ''
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          QA_GENERATED_DIR: @@GEN_DIR@@
          SOURCE_PR: ${{ github.event.pull_request.number }}
        run: |
          git config --global user.name "AI-QA-Agent[bot]"
          git config --global user.email "ai-qa-agent@users.noreply.github.com"
          BRANCH="qa-agent/held-${GITHUB_RUN_ID}"
          git fetch --no-tags origin main
          git checkout -b "$BRANCH" origin/main
          mkdir -p "$QA_GENERATED_DIR"
          cp qa-quarantine/@@SPEC_GLOB@@ "$QA_GENERATED_DIR"/
          git add "$QA_GENERATED_DIR"
          if git diff --staged --quiet; then
            echo "Nothing to open."
            exit 0
          fi
          git commit -m "chore(qa): held-back automation - needs review"
          git push origin "$BRANCH"
          {
            echo "**Draft - do not merge until the decision below is resolved.**"
            echo
            [ -s qa-results/decision.md ] && cat qa-results/decision.md
            echo
            echo "Run: ${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
          } > qa-draft-body.md
          gh pr create --draft --base main --head "$BRANCH" \\
            --title "QA agent (needs review): held-back tests${SOURCE_PR:+ (from #$SOURCE_PR)}" \\
            --body-file qa-draft-body.md \\
            || echo "::warning::Could not open a PR automatically. The tests are on branch $BRANCH."
"""

SPEC_GLOB_BY_PRESET = {"playwright": "*.spec.ts", "cypress": "*.cy.ts", "jest": "*.test.ts", "vitest": "*.test.ts",
                       "pytest": "test_*.py", "cucumber-java": "*.feature"}
REPORT_PATHS = {"cucumber-java": "target/failsafe-reports/\n            target/cucumber-html-report/",
                "playwright": "playwright-report/", "cypress": "cypress/videos/\n            cypress/screenshots/",
                "jest": "coverage/", "vitest": "coverage/", "pytest": "report.xml"}
LANG_SETUP = {"cucumber-java": "java", "playwright": "node", "cypress": "node", "jest": "node", "vitest": "node", "pytest": "python"}


def build_workflow(cfg, preset, lang):
    setup = SETUP[LANG_SETUP.get(preset, "dotnet" if lang == "dotnet" else "node")]
    if lang == "dotnet" and preset in ("playwright", "cypress"):
        setup = SETUP["dotnet"]
    tail = (WORKFLOW_TAIL.replace("@@GEN_DIR@@", cfg["generated_dir"])
            .replace("@@SPEC_GLOB@@", SPEC_GLOB_BY_PRESET.get(preset, "*.spec.ts"))
            .replace("@@REPORT_PATHS@@", REPORT_PATHS.get(preset, "")))
    return WORKFLOW_HEAD + setup + tail


# --------------------------------------------------------------------------- #
def write_safe(path, content, force, log):
    if os.path.exists(path) and not force:
        path = path + ".draft"
        log.append(f"(exists - wrote {path} instead; use --force to overwrite)")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    root = os.path.abspath(args[0] if args else ".")
    force, check = "--force" in argv, "--check" in argv
    files = list(walk(root))
    F = Finding()
    cfg, preset, lang = build_config(root, files, F)
    notes = []
    print("\nQA agent setup review - " + os.path.basename(root))
    print("=" * 60)
    print(f"  {SURE} = found in the repo        {CHECK} = a guess, please check\n")
    for mark, topic, text in F.rows:
        print(f"  {mark} {topic}: {text}")
    if not check:
        cp = write_safe(os.path.join(root, "qa-agent", "qa-agent.config.json"), json.dumps(cfg, indent=2) + "\n", force, notes)
        wp = write_safe(os.path.join(root, ".github", "workflows", "post-merge-qa.yml"), build_workflow(cfg, preset, lang), force, notes)
        print(f"\nWritten: {os.path.relpath(cp, root)}\n         {os.path.relpath(wp, root)}")
        for n in notes:
            print("  " + n)
    todo = sum(1 for m, _, _ in F.rows if m == CHECK)
    print(f"\n{todo} item(s) to check. Next: copy post_merge_qa_agent.py into the repo root, add the AI key as a repository "
          "secret, then run the workflow with dry_run ticked and confirm the right tests are chosen.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
