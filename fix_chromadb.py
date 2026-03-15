"""
fix_chromadb_complete.py

Fixes ALL issues in chromadb/config.py for Python 3.14 in one pass.
Run: python fix_chromadb_complete.py
"""
import sys, re, subprocess, importlib.util, pathlib

# ── Find config.py ────────────────────────────────────────────────────────────
spec = importlib.util.find_spec("chromadb")
if not spec:
    print("ERROR: chromadb not installed"); sys.exit(1)

config_path = pathlib.Path(spec.origin).parent / "config.py"
print(f"Patching: {config_path}")

original = config_path.read_text(encoding="utf-8")
bak = config_path.with_suffix(".py.bak")
bak.write_text(original, encoding="utf-8")
print(f"Backup:   {bak}\n")

lines  = original.splitlines(keepends=True)
out    = []
in_settings = False
fixes  = []


def infer_type(val: str) -> str:
    v = val.strip().rstrip(",")
    if v in ("True", "False"):         return "bool"
    if v == "None":                     return "Optional[Any]"
    if re.match(r'^-?\d+$', v):        return "Optional[int]"
    if re.match(r'^-?\d*\.\d+$', v):   return "Optional[float]"
    if v.startswith(('"', "'")):        return "Optional[str]"
    return "Optional[Any]"


for raw in lines:
    line = raw.rstrip("\r\n")
    eol  = raw[len(line):]

    # ── track Settings class ──────────────────────────────────────────────────
    if re.match(r'^class Settings\b', line):
        in_settings = True
    elif in_settings and line and re.match(r'^[a-zA-Z@]', line):
        in_settings = False

    # ── FIX A: pydantic.v1 imports ────────────────────────────────────────────
    if "from pydantic.v1 import" in line:
        # Extract everything being imported
        names = re.sub(r'from pydantic\.v1 import\s*', '', line).strip()
        name_list = [n.strip() for n in names.split(',')]

        new_lines_here = []
        kept_v1 = []

        for n in name_list:
            if n == 'BaseSettings':
                new_lines_here.append(
                    f"from pydantic_settings import BaseSettings  # py314-fix{eol}"
                )
                fixes.append("Replaced: from pydantic.v1 import BaseSettings")
            elif n == 'validator':
                new_lines_here.append(
                    f"from pydantic import field_validator  # py314-fix{eol}"
                )
                fixes.append("Replaced: validator -> field_validator")
            elif n in ('Field', 'field'):
                new_lines_here.append(
                    f"from pydantic import Field  # py314-fix{eol}"
                )
                fixes.append("Replaced: pydantic.v1 Field -> pydantic Field")
            elif n:
                kept_v1.append(n)

        if kept_v1:
            new_lines_here.append(
                f"from pydantic.v1 import {', '.join(kept_v1)}  # py314-kept{eol}"
            )

        out.extend(new_lines_here)
        continue

    # ── FIX B: @validator(...) decorator ─────────────────────────────────────
    if re.match(r'\s*@validator\s*\(', line):
        # Extract field names (positional string args)
        fields = re.findall(r"['\"]([^'\"]+)['\"]", line)
        fields_str = ", ".join(f'"{f}"' for f in fields)
        indent = re.match(r'^(\s*)', line).group(1)
        out.append(f"{indent}@field_validator({fields_str}, mode='before')  # py314-fix{eol}")
        fixes.append(f"Replaced: @validator -> @field_validator({fields_str})")
        continue

    # ── FIX C: @field_validator with pydantic v1 kwargs ──────────────────────
    if re.match(r'\s*@field_validator\s*\(', line):
        # Remove pre=, always=, allow_reuse= args; keep only field names + mode=
        cleaned = re.sub(r',?\s*\b(pre|always|allow_reuse)\s*=\s*(True|False)', '', line)
        # Ensure mode='before' is present
        if "mode=" not in cleaned:
            cleaned = re.sub(r'\)\s*$', ", mode='before')", cleaned.rstrip())
        out.append(cleaned + eol)
        if cleaned != line:
            fixes.append(f"Cleaned field_validator kwargs: {line.strip()}")
        continue

    # ── FIX D: unannotated fields inside Settings class ───────────────────────
    if in_settings:
        m = re.match(
            r'^(?P<ind>\s+)(?P<n>[a-zA-Z_][a-zA-Z0-9_]*)(?!\s*:)\s*=\s*(?P<val>.+)$',
            line
        )
        if m and not line.strip().startswith('#'):
            name, ind, val = m['n'], m['ind'], m['val']
            if (not name.startswith('__')
                    and 'def ' not in line
                    and 'class ' not in line
                    and name not in ('model_config',)):
                ann = infer_type(val)
                out.append(f"{ind}{name}: {ann} = {val}{eol}")
                fixes.append(f"Annotated field: {name}: {ann}")
                continue

    out.append(raw)

# ── Inject typing import at top ───────────────────────────────────────────────
inject = "from typing import Optional, Any  # py314-fix\n"
insert_pos = 0
for i, l in enumerate(out):
    if l.startswith(('import ', 'from ')):
        insert_pos = i + 1
out.insert(insert_pos, inject)

# ── Write ─────────────────────────────────────────────────────────────────────
config_path.write_text("".join(out), encoding="utf-8")

print(f"Applied {len(fixes)} fixes:")
for f in fixes:
    print(f"  + {f}")

# ── Verify ────────────────────────────────────────────────────────────────────
print("\nVerifying in fresh subprocess...")
verify = """
import warnings; warnings.filterwarnings('ignore')
import chromadb, tempfile, shutil
print(f"IMPORT OK  chromadb {chromadb.__version__}")
tmp = tempfile.mkdtemp()
try:
    c = chromadb.PersistentClient(path=tmp)
    col = c.get_or_create_collection("test")
    col.add(documents=["hello world"], ids=["1"])
    r = col.query(query_texts=["hello"], n_results=1)
    assert r["documents"][0][0] == "hello world"
    print("ROUNDTRIP OK")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
"""
res = subprocess.run([sys.executable, "-c", verify], capture_output=True, text=True)
print(res.stdout.strip())

if res.returncode != 0:
    err = res.stderr.strip()
    # Extract just the key error line
    for l in err.splitlines():
        if "Error" in l or "error" in l or "FAIL" in l:
            print(f"  {l}")

    # Show what's still broken
    patched = "".join(out)
    still_broken = [
        f"  {i:3d}: {l}"
        for i, l in enumerate(patched.splitlines(), 1)
        if "pydantic.v1" in l and "py314-kept" not in l
    ]
    if still_broken:
        print("\nRemaining pydantic.v1 references:")
        print("\n".join(still_broken))

    print("\nRestoring backup...")
    config_path.write_text(original, encoding="utf-8")
    sys.exit(1)
else:
    print("\nSUCCESS — chromadb is working on Python 3.14!")
    print("\nNext:")
    print("  python chromadb_diagnose.py")
    print("  python orchestrator.py --requirements test_data/sample_requirements.csv")