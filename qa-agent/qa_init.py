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
        self.todos = []  # manual steps: dicts with title, path, missing, how, who

    def add(self, mark, topic, text, path="", missing="", how="", who=""):
        """path/missing/how/who describe the manual step behind a CHECK row: where in the config, what, and who knows it."""
        self.rows.append((mark, topic, text))
        if mark == CHECK and path:
            self.todos.append({"title": topic, "path": path, "missing": missing or text, "how": how, "who": who})


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
    F.add(CHECK, "Test framework", "none recognised - set runner.preset by hand", "runner.preset",
          "The test framework was not recognised.", "Set it to one of: playwright, cypress, jest, vitest, pytest, cucumber-java, generic.", "QA automation engineer")
    return "playwright"


SPEC_GLOBS = {"playwright": ["*.spec.ts", "*.spec.js"], "cypress": ["*.cy.ts", "*.cy.js"], "jest": ["*.test.ts", "*.test.js", "*.spec.ts"],
              "vitest": ["*.test.ts", "*.test.js", "*.spec.ts"], "pytest": ["test_*.py", "*_test.py"], "cucumber-java": ["*.feature"]}


def detect_tests(files, preset, F):
    globs = SPEC_GLOBS.get(preset, ["*.spec.ts"])
    specs = [f for f in files if any(fnmatch.fnmatch(os.path.basename(f), g) for g in globs)
             and not re.search(r"(^|/)(generated|qa-quarantine)/", f)]  # the agent's own output is not the suite
    if not specs:
        F.add(CHECK, "Test folder", "no test files found", "e2e_dir",
              "No test files were found, so the test folder is unknown.", "Put the folder that holds the automated tests, e.g. \"tests\" or \"src/test/resources/scenarios\".", "QA automation engineer")
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
        if "/" not in f:  # a file in the repo root (a config file) is not a source folder
            continue
        top = f.split("/")[0]
        counts[top] = counts.get(top, 0) + 1
        exts[ext] = exts.get(ext, 0) + 1
    if not counts:
        return "src", [".py"], F.add(CHECK, "Source folder", "no application code found", "src_dir",
                                    "No application code was found in this repository (the tests may target a separately deployed site).",
                                    "If the application code is in this repo, put its root folder in \"src_dir\" and its file types in \"source_extensions\". "
                                    "If not, leave it: impact analysis then relies on the changed files you pass in.", "Developer") or "other"
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
    # the tests themselves usually say where the app runs: http://localhost:8080
    seen = {}
    for f in files:
        if re.search(r"(^|/)(test|tests|e2e|cypress)(/|$)", f) and f.endswith((".java", ".kt", ".cs", ".py", ".ts", ".js")):
            for m in re.finditer(r"(?:localhost|127\.0\.0\.1):(\d{2,5})", read(root, f, 20000)):
                seen.setdefault(int(m.group(1)), f)
    if seen:
        port = max(seen, key=lambda p: sum(1 for q in seen if q == p))
        F.add(SURE, "App port", f"{port} (from the tests: {seen[port]})")
        return port
    default = {"java": 8080, "node": 3000, "dotnet": 5000, "python": 8000}.get(lang, 8080)
    F.add(CHECK, "App port", f"{default} assumed - no port setting found, confirm it", "app_port",
          f"The port the application listens on was not found in any setting file; {default} is only a typical default.",
          "Put the port the tests use to reach the app, e.g. 8080.", "Developer or QA lead")
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


SHARED_PREF = ["system", "shared", "common", "core", "app", "root", "infrastructure", "base", "config", "util", "utils", "lib",
               "domain", "model", "models"]


def pick_shared(comps):
    """The component that holds cross-cutting code and pages with no owner."""
    return next((c for p in SHARED_PREF for c in comps if c.lower() == p), None)


def detect_components(root, files, src, exts, F):
    base, subs, direct = top_dirs_with_code(root, files, src, exts)
    skip = {"test", "tests", "resources", "static", "assets", "public"}
    subs = [s for s in subs if s.lower() not in skip]
    comps = {s: [f"{base}/{s}"] for s in subs}
    if direct:  # files sitting directly in the base folder (the application entry class and the like) are cross-cutting
        rootfiles = [f for f in files if f.startswith(base + "/") and f.count("/") == base.count("/") + 1
                     and os.path.splitext(f)[1] in exts]
        comps.setdefault(pick_shared(comps) or "app", []).extend(rootfiles)
    if not comps:
        F.add(CHECK, "Components", "no sub-folders found - everything is treated as one component", "components",
              "The code has no sub-folders to split into areas.", "Add areas by hand: \"components\": {\"orders\": [\"src/orders\"], \"users\": [\"src/users\"]}.", "Developer")
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
    code_owner = {}  # lower-case class name -> component, for the code files inside the components' own folders
    for c, dirs in comps.items():
        for f in files:
            if f.endswith((".java", ".cs", ".py", ".ts")) and any(f.startswith(d + "/") for d in dirs if "<root" not in d):
                code_owner.setdefault(os.path.splitext(os.path.basename(f))[0].lower(), c)

    def owner_by_code(name):
        st = stem(name)
        hits = {c for cls, c in code_owner.items() if cls.startswith(st) or stem(cls).startswith(st)}
        return hits.pop() if len(hits) == 1 else None

    shared = pick_shared(comps)  # where pages with no owner go
    unplaced, by_code = [], []
    items = [(d, d.split("/")[-1], None) for d in sorted(ui_dirs) if d != parent]
    items += [(f, os.path.splitext(os.path.basename(f))[0], f) for f in ui_dirs.get(parent, [])]
    for path, leaf, is_file in items:
        hit = next((c for c in comps if stem(c) == stem(leaf)), None)
        if hit:
            comps[hit].append(path)
            continue
        hit = owner_by_code(leaf)
        if hit:
            comps[hit].append(path)
            by_code.append(f"{leaf} -> {hit}")
        elif shared:
            comps[shared].append(path)
            unplaced.append(leaf)
    if by_code:
        F.add(SURE, "Pages placed by the code that serves them", ", ".join(by_code))
    if unplaced:
        F.add(CHECK, "Pages with no matching code", ", ".join(unplaced) + f" - treated as shared (added to '{shared}'); move them if one area owns them",
              f"components.{shared}", f"These pages could not be tied to any code area: {', '.join(unplaced)}. They were put under '{shared}'.",
              "If a page belongs to one area, move its path from this list into that area's list.", "Developer")
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
    F.add(CHECK, "Which tests each area affects", "\n        ".join(lines), "spec_map",
          "The test-to-area mapping was guessed from names, shared page paths and the code.",
          "Read each line; add or remove test names under the right area.", "QA lead (knows what each test covers)")
    if unsure_specs:
        F.add(CHECK, "Tests that matched no area", ", ".join(unsure_specs) +
              " - they run only for shared areas (" + (", ".join(shared) or "none") + "); say which area they belong to",
              "spec_map.<area>", f"No area matched these tests by name or by page: {', '.join(unsure_specs)}.",
              "Add each test name to the list of the area it covers, e.g. \"spec_map\": {\"owner\": [\"FindOwners\", \"" + unsure_specs[0] + "\"]}.",
              "QA lead (knows what each test covers)")
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


CODE_FILE_EXTS = (".java", ".kt", ".cs", ".py", ".ts", ".tsx", ".js", ".jsx")


def component_code(root, files, comp_cfg):
    """component -> its code files, and class name -> defining component."""
    cfiles, defined = {}, {}
    for c, dirs in comp_cfg.items():
        fs = [f for f in files if f.endswith(CODE_FILE_EXTS) and any(f == d or f.startswith(d + "/") for d in dirs)]
        cfiles[c] = fs
        for f in fs:
            name = os.path.splitext(os.path.basename(f))[0]
            if len(name) >= 4:
                defined.setdefault(name, c)
    return cfiles, defined


def analyse_dependencies(root, cfiles, defined, entry_names):
    """Which components use classes of which others; which classes are used almost everywhere (base/shared types)."""
    text = {c: "\n".join(read(root, f, 30000) for f in fs) for c, fs in cfiles.items()}
    uses = {}  # class -> set of OTHER components whose code mentions it
    for name, owner in defined.items():
        rx = re.compile(r"\b" + re.escape(name) + r"\b")
        uses[name] = {c for c, t in text.items() if c != owner and rx.search(t)}
    n = len(cfiles)
    need = max(2, -(-int((n - 1) * 0.4 * 10) // 10))
    generic = {nm for nm, cs in uses.items() if len(cs) >= need} | set(entry_names)
    changed = True
    while changed:  # the parent class of a shared class is shared too (NamedEntity -> BaseEntity)
        changed = False
        for nm in list(generic):
            owner = defined.get(nm)
            for f in cfiles.get(owner, []):
                if os.path.splitext(os.path.basename(f))[0] == nm:
                    m = re.search(r"\bextends\s+(\w+)|class\s+\w+\s*:\s*(\w+)", read(root, f, 6000))
                    parent = (m.group(1) or m.group(2)) if m else None
                    if parent and parent in defined and parent not in generic:
                        generic.add(parent)
                        changed = True
    deps = {}  # A -> components A depends on
    for name, cs in uses.items():
        if name in generic:
            continue
        for a in cs:
            deps.setdefault(a, set()).add(defined[name])
    return deps, generic


def expand_by_dependencies(mapping, deps, shared):
    """A change in B can break whatever A tests when A uses B: B inherits A's tests."""
    out = {c: list(v) for c, v in mapping.items()}
    added = {}
    changed = True
    while changed:
        changed = False
        for a, bs in deps.items():
            for b in bs:
                if b in shared or a == b or b not in out:
                    continue
                for t in out.get(a, []):
                    if t not in out[b]:
                        out[b].append(t)
                        added.setdefault(b, set()).add(f"{t} (via {a})")
                        changed = True
    return out, added


def leftover_resources(files, comp_cfg, ui_parents, shared):
    """Resource folders no component owns (message bundles and the like): shared by default."""
    skip = {"static", "db", "templates", "META-INF", "public", "assets"}
    taken = {d for dirs in comp_cfg.values() for d in dirs}
    out = []
    for f in files:
        m = re.match(r"^(.*?/resources)/([^/]+)(/|$)", f)
        if not m or "/test/" in f:
            continue
        top, name = m.group(1), m.group(2)
        path = f"{top}/{name}"
        if name in skip or re.match(r"(application|bootstrap|banner|logback|log4j)", name) or path in taken or path in out:
            continue
        if any(path == p or path.startswith(p + "/") for p in ui_parents):
            continue
        if name.endswith((".sql", ".xml", ".yml", ".yaml")):
            continue
        out.append(path)
    return out


def extract_code_facts(root, files, F):
    """Routes the code serves and messages it sets explicitly (for the AI's app rules)."""
    routes, msgs = [], []
    pats = [r'@(?:Get|Post|Put|Delete|Request)Mapping\(\s*(?:value\s*=\s*)?"(/[^"]*)"', r'@page\s+"(/[^"]*)"',
            r"(?:app|router)\.(?:get|post|put|delete)\(\s*['\"](/[^'\"]*)['\"]", r'@(?:app|bp|router)\.route\(\s*["\'](/[^"\']*)["\']']
    for f in files:
        if not f.endswith(CODE_FILE_EXTS + (".razor",)) or "/test/" in f:
            continue
        t = read(root, f, 40000)
        for p in pats:
            routes += re.findall(p, t)
        msgs += re.findall(r'\bmessage\s*=\s*"([^"]{4,120})"', t)
    routes = list(dict.fromkeys(routes))
    msgs = list(dict.fromkeys(msgs))
    if routes:
        F.add(SURE, "Pages the code serves (for the AI)", f"{len(routes)} routes found, e.g. " + ", ".join(routes[:4]))
    if msgs:
        F.add(SURE, "Messages set in code (for the AI)", "; ".join(msgs[:4]))
    return routes, msgs


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


def detect_seed_data(root, files, F):
    out = []
    cands = [f for f in files if os.path.basename(f).lower() in ("data.sql", "import.sql")
             or re.match(r"(seed|fixtures?).*\.(json|sql)$", os.path.basename(f).lower())]
    props = " ".join(read(root, f, 4000) for f in files if os.path.basename(f).startswith("application") and f.endswith((".properties", ".yml", ".yaml")))
    used = lambda f: bool(re.search(r"/(hsqldb|h2|mysql|postgres|postgresql|sqlite)/", f)) and re.search(
        r"/(\w+)/[^/]+$", f).group(1).lower() in props.lower()
    cands.sort(key=lambda f: (0 if used(f) else 1, 0 if re.search(r"hsqldb|h2", f) else 1, f))  # the database the app uses
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
        F.add(CHECK, "Seeded test data", "none found - if the app starts with data, name that file under test_data", "test_data",
          "No seed or fixture file was found. If the app starts with data, the AI cannot see it and may use names that do not exist.",
          "Add the file: \"test_data\": [{\"file\": \"path/to/seed.json\", \"title\": \"Seeded data\", \"note\": \"the only data at start-up\"}]. Skip it if the app starts empty.",
          "Developer or QA lead")
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
        F.add(CHECK, "Login", "the code mentions login - if tests need a logged-in user, fill login_setup and auth_specs", "login_setup",
          "The code mentions login, but no login setup file for the tests was found.",
          "Put the test setup that logs in and saves the session in \"login_setup\", and list the tests that need it in \"auth_specs\". Skip both if the tests run anonymously.",
          "QA automation engineer")
        return "", False
    F.add(SURE, "Login", "no login found - tests run anonymously")
    return "", True


def extract_ui_facts(root, files, ui_parent, F):
    """Headings, form ids and field names from the page templates -> app_rules for the AI."""
    heads, forms, fields, links = {}, set(), set(), set()
    btn_links, buttons = set(), set()
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
        for attrs, label in re.findall(r"<a([^>]*)>\s*([A-Z][A-Za-z ]{2,30}?)\s*</a>", t):
            (btn_links if re.search(r"class=\"[^\"]*\bbtn\b", attrs) else links).add(label)
        for block in re.findall(r"<button\b(.*?)</button>", t, re.S):
            inner = re.sub(r"<[^>]+>", " ", block.split(">", 1)[-1]).strip()
            lits = re.findall(r"'([A-Z][A-Za-z ]{2,30})'", block)
            buttons |= ({inner} if re.match(r"^[A-Z][A-Za-z ]{2,30}$", inner) else set(lits))
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
    if btn_links:
        bits.append("Links styled as buttons (click them as LINKS, not buttons): " + ", ".join(f"'{x}'" for x in sorted(btn_links)[:10]) + ".")
    if buttons:
        bits.append("Form submit buttons: " + ", ".join(f"'{x}'" for x in sorted(buttons)[:10]) + ".")
    if bits:
        F.add(SURE, "Pages, forms and fields (for the AI)", f"{len(pages)} page files read: headings, form ids, field names")
    return " ".join(bits)


def readme_summary(root, files):
    """One sentence on what the application is: the About/Overview section, else the text right under the title."""
    for f in files:
        if os.path.basename(f).lower() not in ("readme.md", "readme"):
            continue
        text = read(root, f, 12000).replace("\r\n", "\n")
        sections, head, buf = [], "", []
        for line in text.split("\n"):
            m = re.match(r"^#{1,3}\s+(.*)$", line)
            if m:
                sections.append((head, "\n".join(buf)))
                head, buf = m.group(1).strip().lower(), []
            else:
                buf.append(line)
        sections.append((head, "\n".join(buf)))
        order = [b for h, b in sections if re.search(r"about|overview|description|introduction|what is", h)]
        order += [b for h, b in sections if not re.search(r"install|run|build|setup|usage|getting started|prereq|licen|contribut|test|docker", h)]
        for body in order:
            for para in re.split(r"\n\s*\n", body):
                para = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", para)          # [text](url) -> text
                para = " ".join(para.split())
                if (len(para.split()) >= 6 and not para.startswith(("```", "*", "-", "|", "<", "!", "You can", "To ", "Run", "Use "))
                        and "http" not in para and "```" not in para):
                    return para[:400]
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
    data = detect_seed_data(root, files, F)
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
    shared_name = pick_shared(comp_cfg)
    # resource folders nobody owns (message bundles): shared
    if shared_name and ui_parents:
        extra = leftover_resources(files, comp_cfg, ui_parents, shared_name)
        if extra:
            comp_cfg[shared_name].extend(extra)
            F.add(SURE, "Resource folders with no owner", ", ".join(extra) + f" - added to '{shared_name}'")
    # who uses whom: a change in a component affects the tests of the components that use it
    entry_names = []
    if lang == "java":
        entry_names = [os.path.splitext(os.path.basename(f))[0] for f in files if f.endswith(".java") and "/test/" not in f
                       and re.search(r"@SpringBootApplication|public static void main", read(root, f, 6000))]
    generic_found = []
    if len(comp_cfg) > 1:
        cfiles, defined = component_code(root, files, comp_cfg)
        deps, generic_set = analyse_dependencies(root, cfiles, defined, entry_names)
        generic_found = sorted(generic_set)
        shared_set = {c for c in comp_cfg if c.lower() in SHARED_WORDS}
        mapping, added = expand_by_dependencies(mapping, deps, shared_set)
        if deps:
            F.add(SURE, "Which areas use which (from the code)", "; ".join(f"{a} uses {', '.join(sorted(bs))}" for a, bs in sorted(deps.items())))
        for b, items in sorted(added.items()):
            F.add(CHECK, "Tests added because other areas use this one", f"{b} also affects: " + ", ".join(sorted(items)) + " - check",
                  f"spec_map.{b}", f"The code of other areas uses '{b}', so its mapping was extended with: {', '.join(sorted(items))}.",
                  "Keep the extra tests if a change in this area can really break them; delete them from the list if not.", "Developer")
        if generic_found:
            F.add(SURE, "Shared types (ignored when tracing impact)", ", ".join(generic_found))
    routes, code_msgs = extract_code_facts(root, files, F)
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
            "app_rules": (ui_facts + (" Pages the code serves: " + ", ".join(routes[:25]) + "." if routes else "")
                          + (" Messages set explicitly in the code: " + "; ".join(f"'{m}'" for m in code_msgs[:8]) + "." if code_msgs else "")
                          + " " + rules["extra"] + " Take element names, labels and headings from the provided markup only. "
                          "Exact validation messages were not detected - use only messages that appear in the markup or test data.").strip(),
        },
    }
    if generic_found:
        cfg["generic_types"] = generic_found
    if lang != "java":
        cfg.pop("components")
        cfg.pop("support_dirs")
    if preset != "cucumber-java":
        cfg.pop("no_login", None)
        cfg.pop("default_owner", None)
    F.add(CHECK, "Project description", "taken from the README - check it describes the app" if desc else "FILL IN project_description",
          "project_description", "A short description of what the application does (the AI reads it for context)." + ("" if desc else " None was found in the README."),
          "Write one or two sentences: what the app is, who uses it, its main pages. Also check \"suite_description\".", "Anyone who knows the product")
    F.add(CHECK, "Validation messages", "not detectable from code. After the first run, add the exact messages the app shows to prompt_vars.app_rules",
          "prompt_vars.app_rules", "The exact wording of validation and error messages that come from the framework (for example 'must not be empty'). The code does not state them.",
          "Append to the text: \"Exact messages: an empty required field shows 'must not be empty'; a bad telephone shows '...'.\" Copy them from the running app.",
          "QA lead (has seen the messages in the app)")
    cfg["_todo"] = [f"{t['path']}: {t['missing']}" for t in F.todos]
    return cfg, preset, lang


def todo_markdown(F, project):
    lines = [f"# Setup to-do for {project}", "",
             "`qa_init.py` filled in most of `qa-agent/qa-agent.config.json` from the repository. The items below are the things it "
             "could not work out. Each one says what is missing, where in the config file to put it, and who usually knows it.", ""]
    if not F.todos:
        lines.append("Nothing is missing. Run the workflow once with dry_run ticked and check that the right tests are chosen.")
    for i, t in enumerate(F.todos, 1):
        lines += [f"## {i}. {t['title']}", "",
                  f"- **What is missing:** {t['missing']}",
                  f"- **Where to update:** `qa-agent/qa-agent.config.json` > `{t['path']}`",
                  f"- **What to put there:** {t['how'] or 'Check the value and correct it if needed.'}",
                  f"- **Who usually knows:** {t['who'] or 'Project owner'}", ""]
    lines += ["When every item is done, delete the `_todo` and `_comment` lines from the config, then run the workflow with "
              "dry_run ticked and check that the right tests are chosen.", ""]
    return "\n".join(lines)


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
    if F.todos:
        print("\n  To fill in (what is missing -> where in the config file):")
        for t in F.todos:
            print(f"    - {t['path']}  <-  {t['missing'][:110]}")
    if not check:
        tp = write_safe(os.path.join(root, "qa-agent", "SETUP-TODO.md"), todo_markdown(F, os.path.basename(root)), force, notes)
        print(f"         {os.path.relpath(tp, root)}  (the list above, with details)")
    todo = sum(1 for m, _, _ in F.rows if m == CHECK)
    print(f"\n{todo} item(s) marked {CHECK} ({len(F.todos)} need a manual edit - see qa-agent/SETUP-TODO.md). Next: copy post_merge_qa_agent.py into the repo root, add the AI key as a repository "
          "secret, then run the workflow with dry_run ticked and confirm the right tests are chosen.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
