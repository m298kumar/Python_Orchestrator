"""
chromadb_diagnose.py
Run this standalone: python chromadb_diagnose.py
No project files needed.
"""
import sys
import subprocess

W = "\033[93m"; G = "\033[92m"; R = "\033[91m"; B = "\033[96m"; X = "\033[0m"
def ok(m):   print(f"  {G}OK   {m}{X}")
def bad(m):  print(f"  {R}FAIL {m}{X}")
def warn(m): print(f"  {W}WARN {m}{X}")
def hdr(m):  print(f"\n{B}--- {m} ---{X}")

hdr("1. Python version")
pv = sys.version_info
print(f"  {sys.version}")
if pv >= (3, 14):
    warn("Python 3.14 detected — need chromadb>=0.6.0 (pydantic-v1 was removed)")
else:
    ok(f"Python {pv.major}.{pv.minor}")

hdr("2. Installed packages")
r = subprocess.run(
    [sys.executable, "-m", "pip", "show", "chromadb", "pydantic", "pydantic-settings"],
    capture_output=True, text=True
)
for line in r.stdout.splitlines():
    if line.startswith(("Name:", "Version:")):
        print(f"  {line}")

hdr("3. pydantic version check")
try:
    import pydantic
    v = int(pydantic.__version__.split(".")[0])
    (ok if v >= 2 else bad)(f"pydantic {pydantic.__version__} ({'V2 good' if v>=2 else 'V1 — upgrade!'})")
except ImportError:
    bad("pydantic not installed")

try:
    import pydantic_settings
    ok(f"pydantic-settings {pydantic_settings.__version__}")
except ImportError:
    bad("pydantic-settings missing  ->  pip install pydantic-settings>=2.0.0")

hdr("4. chromadb import (this is where the crash usually happens)")
try:
    import chromadb
    ok(f"chromadb {chromadb.__version__} imported OK")
    major, minor = (int(x) for x in chromadb.__version__.split(".")[:2])
    if (major, minor) < (0, 6):
        warn(f"chromadb {chromadb.__version__} — upgrade to >=0.6.0 for Python 3.14")
    else:
        ok("Version is pydantic-v2 native — no patching needed")
except Exception as e:
    bad(f"import chromadb FAILED: {e}")
    print(f"\n  {R}Fix: pip install --upgrade 'chromadb>=0.6.0'{X}\n")
    sys.exit(1)

hdr("5. PersistentClient roundtrip")
import tempfile, shutil
tmp = tempfile.mkdtemp(prefix="chroma_diag_")
try:
    client = chromadb.PersistentClient(path=tmp)
    ok("PersistentClient created")
    col = client.get_or_create_collection("diag")
    col.add(documents=["hello world"], ids=["doc1"])
    res = col.query(query_texts=["hello"], n_results=1)
    assert res["documents"][0][0] == "hello world"
    ok("add + query roundtrip works")
    client.delete_collection("diag")
except Exception as e:
    bad(f"Roundtrip failed: {e}")
    import traceback; traceback.print_exc()
finally:
    shutil.rmtree(tmp, ignore_errors=True)

hdr("6. Embedding functions")
from chromadb.utils import embedding_functions as ef
for name, mk in [
    ("SentenceTransformerEmbeddingFunction",
     lambda: ef.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")),
    ("DefaultEmbeddingFunction", lambda: ef.DefaultEmbeddingFunction()),
    ("ONNXMiniLM_L6_V2",        lambda: ef.ONNXMiniLM_L6_V2()),
]:
    try:
        mk(); ok(f"{name} available"); break
    except Exception as e:
        warn(f"{name}: {e.__class__.__name__}")

hdr("Fix commands (run if anything above failed)")
print(f"""
  {B}Upgrade chromadb to drop pydantic.v1 entirely:{X}
  pip install --upgrade "chromadb>=0.6.0" "pydantic>=2.0.0" "pydantic-settings>=2.0.0"

  {B}Optional — better local embeddings:{X}
  pip install sentence-transformers onnxruntime

  {B}Nuclear option — clean reinstall:{X}
  pip uninstall chromadb pydantic pydantic-settings -y
  pip install "chromadb>=0.6.0" "pydantic>=2.0.0" "pydantic-settings>=2.0.0"
""")