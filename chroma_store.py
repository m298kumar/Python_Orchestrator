"""
ChromaDB Vector Store  v2
Three collections: requirements, tc_examples, domain_vocab.
"""

#import pydantic_v1_patch
#pydantic_v1_patch.apply()

import os, re, uuid, json, logging, warnings, requests
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore", category=DeprecationWarning, module="chromadb")
warnings.filterwarnings("ignore", message=".*pydantic.*", category=UserWarning)
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("onnxruntime").setLevel(logging.ERROR)

from rich.console import Console
from config import config
from requirements_reader import Requirement

console = Console()

# ── client factory ────────────────────────────────────────────────────────────

def _make_client(path):
    """
    Create a ChromaDB PersistentClient.

    ChromaDB's Settings class inherits from pydantic-settings BaseSettings with
    extra='forbid'. pydantic-settings reads ALL environment variables at Settings()
    instantiation time — which happens at import time (class-level default in
    shared_system_client.py). Since load_dotenv() has already run, every key in
    our .env (OLLAMA_BASE_URL, CHROMA_PERSIST_DIR, OUTPUT_DIR, …) is in os.environ,
    causing a ValidationError for each unrecognised key.

    Fix: temporarily clear os.environ so ChromaDB Settings sees nothing unexpected,
    then restore everything in the finally block.
    """
    # ChromaDB Settings (pydantic-settings BaseSettings) reads BOTH os.environ
    # AND the .env file in CWD.  Our .env has vars chromadb doesn't recognise
    # and Settings has extra='forbid', causing ValidationError on import.
    #
    # Three call-sites trigger Settings() instantiation:
    #   chromadb/__init__.py line ~109  : __settings = Settings()  [module level]
    #   shared_system_client.py         : settings: Settings = Settings()  [class level]
    #   PersistentClient() body         : settings = Settings()  [if not passed in]
    #
    # Fix:
    #   1. Remove our .env keys from os.environ (suppress env-var source)
    #   2. Change CWD to a temp dir so pydantic-settings can't find our .env
    #   3. Import chromadb and pre-build a Settings object while env is clean
    #   4. Restore CWD + env vars
    #   5. Create the client passing the pre-built Settings → skips internal Settings()
    import tempfile

    try:
        from dotenv import dotenv_values
        _dot_env_keys = set(dotenv_values().keys())
    except Exception:
        _dot_env_keys = set()

    _saved_env = {k: os.environ.pop(k) for k in _dot_env_keys if k in os.environ}
    _orig_cwd = os.getcwd()
    _tmpdir = tempfile.mkdtemp()

    try:
        os.chdir(_tmpdir)
        import chromadb
        # Resolve to absolute path now, before CWD is restored
        abs_path = path if os.path.isabs(path) else os.path.join(_orig_cwd, path)
        _settings = chromadb.Settings(
            is_persistent=True,
            persist_directory=abs_path,
            allow_reset=True,
            anonymized_telemetry=False,
        )
    except Exception as e:
        raise RuntimeError(
            f"Could not create ChromaDB PersistentClient at '{path}': {e}\n"
            "Try: pip install --upgrade 'chromadb>=0.5.3'"
        ) from e
    finally:
        os.chdir(_orig_cwd)
        try:
            os.rmdir(_tmpdir)
        except Exception:
            pass
        os.environ.update(_saved_env)

    # Client() accepts a pre-built Settings object — no internal Settings() call
    try:
        return chromadb.Client(_settings)
    except Exception as e:
        raise RuntimeError(
            f"Could not create ChromaDB PersistentClient at '{path}': {e}\n"
            "Try: pip install --upgrade 'chromadb>=0.5.3'"
        ) from e

# ── embedding ─────────────────────────────────────────────────────────────────

def _ollama_ok(model, url):
    try:
        tags = requests.get(url.replace("/api/embeddings", "/api/tags"), timeout=5)
        if tags.status_code != 200: return False
        base = model.split(":")[0]
        return any(m == model or m.startswith(base+":") for m in [m["name"] for m in tags.json().get("models",[])])
    except Exception:
        return False

def _ollama_live(model, url):
    try:
        r = requests.post(url, json={"model": model, "prompt": "test"}, timeout=30)
        return r.status_code == 200 and "embedding" in r.json()
    except Exception:
        return False

def _best_embedding_fn():
    from chromadb.utils import embedding_functions as ef
    cfg = config.chromadb
    if cfg.embedding_backend == "ollama":
        m, u = cfg.ollama_embedding_model, cfg.ollama_embedding_url
        console.print(f"[cyan]Checking Ollama embedding:[/cyan] {m}")
        if _ollama_ok(m, u) and _ollama_live(m, u):
            try:
                fn = ef.OllamaEmbeddingFunction(model_name=m, url=u)
                console.print(f"[green]Embedding:[/green] Ollama / {m}")
                return fn
            except Exception as e:
                console.print(f"[yellow]OllamaEmbeddingFunction error: {e}[/yellow]")
        else:
            console.print(f"[yellow]'{m}' not available — run: ollama pull {m}[/yellow]")
    try:
        fn = ef.SentenceTransformerEmbeddingFunction(model_name=cfg.sentence_transformer_model)
        console.print(f"[green]Embedding:[/green] SentenceTransformer / {cfg.sentence_transformer_model}")
        return fn
    except Exception:
        pass
    try:
        fn = ef.DefaultEmbeddingFunction()
        console.print("[green]Embedding:[/green] DefaultEmbeddingFunction (ONNX MiniLM)")
        return fn
    except Exception:
        pass
    console.print("[yellow]No embedding function — ChromaDB using internal default[/yellow]")
    return None

# ── domain vocabulary extractor ───────────────────────────────────────────────

_SCREEN_RE = [
    r"\b([A-Z][a-zA-Z\s]{2,35})\s+(?:screen|page|view|panel|modal|dialog|form|overlay)\b",
    r"\b([A-Z][a-zA-Z\s]{2,30})\s+Screen\b",
    r"(?:navigates?\s+to|opens?\s+the|launches?\s+the|displays?\s+the)\s+([A-Z][a-zA-Z\s]{2,35})",
]
_ELEM_RE = [
    r"['\"]([A-Za-z][A-Za-z\s\-]{1,25})['\"]",
    r"\b([A-Z][a-zA-Z\s]{1,20})\s+(?:button|field|label|input|toggle|checkbox|dropdown|link|tab)\b",
]
_SKIP_WORDS = {"the","this","that","each","every","any","all","customer","user","system","app"}

def _extract_vocab(req):
    text = " ".join([req.title, req.description] + (req.acceptance_criteria or []))
    screens, elements = set(), set()
    for p in _SCREEN_RE:
        for m in re.findall(p, text):
            t = m.strip()
            if 5 < len(t) < 60 and t.lower() not in _SKIP_WORDS:
                screens.add(t.title())
    for p in _ELEM_RE:
        for m in re.findall(p, text, re.IGNORECASE):
            t = m.strip()
            if 3 < len(t) < 40:
                elements.add(t)
    return {
        "screens": list(screens), "elements": list(elements),
        "category": (req.category or req.req_id).lower(),
        "req_id": req.req_id, "req_title": req.title,
    }

# ── TC example formatter ──────────────────────────────────────────────────────

def _tc_to_doc(tc):
    steps = ""
    for i, s in enumerate(tc.get("steps", []), 1):
        a = s.get("action","") if isinstance(s, dict) else str(s)
        r = s.get("expected_result","") if isinstance(s, dict) else ""
        steps += f"  {i}. {a} -> {r}\n"
    return (
        f"title: {tc.get('title','')}\n"
        f"test_type: {tc.get('test_type','')}\n"
        f"ac_type: {tc.get('ac_type','')}\n"
        f"description: {tc.get('description','')}\n"
        f"preconditions: {tc.get('preconditions','')}\n"
        f"given: {tc.get('given','')}\n"
        f"when: {tc.get('when','')}\n"
        f"then: {tc.get('then','')}\n"
        f"steps:\n{steps}"
        f"expected_outcome: {tc.get('expected_outcome','')}\n"
        f"component: {tc.get('component','')}\n"
    )

# ── Vector store ──────────────────────────────────────────────────────────────

class RequirementsVectorStore:

    COLL_REQS  = "requirements"
    COLL_TCS   = "tc_examples"
    COLL_VOCAB = "domain_vocab"

    def __init__(self):
        self._client = self._embed_fn = None
        self._coll_reqs = self._coll_tcs = self._coll_vocab = None
        self._ready = False

    def initialize(self):
        if self._ready:
            return
        try:
            console.print("[cyan]Initialising ChromaDB (3 collections)...[/cyan]")
            os.makedirs(config.chromadb.persist_directory, exist_ok=True)
            self._client   = _make_client(config.chromadb.persist_directory)
            self._embed_fn = _best_embedding_fn()

            def _gc(name):
                kw = {"name": name, "metadata": {"hnsw:space": "cosine"}}
                if self._embed_fn:
                    kw["embedding_function"] = self._embed_fn
                try:
                    return self._client.get_or_create_collection(**kw)
                except Exception:
                    kw.pop("metadata", None)
                    return self._client.get_or_create_collection(**kw)

            self._coll_reqs  = _gc(self.COLL_REQS)
            self._coll_tcs   = _gc(self.COLL_TCS)
            self._coll_vocab = _gc(self.COLL_VOCAB)
            self._ready = True
            console.print(
                f"[green]ChromaDB ready[/green] — "
                f"requirements:{self._coll_reqs.count()} "
                f"tc_examples:{self._coll_tcs.count()} "
                f"domain_vocab:{self._coll_vocab.count()}"
            )
        except ImportError:
            raise ImportError("pip install 'chromadb>=0.5.3' 'pydantic-settings>=2.0.0'")
        except Exception as exc:
            raise RuntimeError(f"ChromaDB init failed: {exc}") from exc

    # ── Collection 1: Requirements ────────────────────────────────────────────

    def add_requirements(self, requirements):
        self.initialize()
        if not requirements:
            return
        docs, metas, ids = [], [], []
        for req in requirements:
            ids.append(f"{req.req_id}_{uuid.uuid4().hex[:8]}")
            docs.append(req.to_chroma_document())
            metas.append({"req_id": req.req_id, "title": req.title,
                           "priority": req.priority, "category": req.category,
                           "tags": ",".join(req.tags)})
        self._coll_reqs.add(documents=docs, metadatas=metas, ids=ids)
        console.print(f"[green]Added {len(requirements)} requirement(s)[/green]")

    def search_similar(self, query, n_results=3, filter_metadata=None):
        self.initialize()
        count = self._coll_reqs.count()
        if count == 0:
            return []
        kw = {"query_texts": [query], "n_results": min(n_results, count),
               "include": ["documents", "metadatas", "distances"]}
        if filter_metadata:
            kw["where"] = filter_metadata
        res = self._coll_reqs.query(**kw)
        if not res["documents"] or not res["documents"][0]:
            return []
        return [{"document": d, "metadata": m, "similarity_score": round(1 - dist, 4)}
                for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]

    def get_context_for_requirement(self, requirement):
        similar = self.search_similar(requirement.to_chroma_document(), n_results=3)
        lines = []
        for item in similar:
            if item["similarity_score"] > 0.3:
                m = item["metadata"]
                lines.append(f"- [{m['req_id']}] {m['title']} (similarity: {item['similarity_score']})")
        return "\n".join(lines) if lines else ""

    # ── Collection 2: TC Examples ─────────────────────────────────────────────

    def store_approved_tc(self, tc_dict, ac_type, test_type, domain=""):
        """Store an approved TC as a few-shot example. Returns doc_id."""
        self.initialize()
        tc_dict = dict(tc_dict)
        tc_dict.update({"ac_type": ac_type, "test_type": test_type, "domain": domain})
        doc_id = f"ex_{ac_type}_{test_type}_{uuid.uuid4().hex[:8]}"
        meta = {
            "ac_type": ac_type, "test_type": test_type, "domain": domain,
            "title": tc_dict.get("title","")[:120],
            "component": tc_dict.get("component",""),
            "tc_json": json.dumps(tc_dict, ensure_ascii=False)[:3000],
        }
        self._coll_tcs.add(documents=[_tc_to_doc(tc_dict)], metadatas=[meta], ids=[doc_id])
        console.print(f"[green]Stored example TC:[/green] {doc_id} ({ac_type}/{test_type})")
        return doc_id

    def retrieve_examples(self, ac_text, ac_type, test_type, n=2):
        """
        Retrieve n closest approved TCs matching ac_type + test_type.
        Returns list of TC dicts for few-shot injection.
        Falls back to any test_type match if filtered set is empty.
        """
        self.initialize()
        count = self._coll_tcs.count()
        if count == 0:
            return []

        query = f"{ac_type} {test_type} {ac_text[:200]}"

        # Attempt 1: exact type match
        for where in [
            {"$and": [{"ac_type": ac_type}, {"test_type": test_type}]},
            {"ac_type": ac_type},
            None,
        ]:
            try:
                kw = {"query_texts": [query], "n_results": min(n, count),
                       "include": ["metadatas", "distances"]}
                if where:
                    kw["where"] = where
                res = self._coll_tcs.query(**kw)
                if res["documents"] and res["documents"][0]:
                    examples = []
                    for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
                        tj = meta.get("tc_json","")
                        if not tj:
                            continue
                        try:
                            tc = json.loads(tj)
                            tc["_similarity"] = round(1 - dist, 4)
                            examples.append(tc)
                        except json.JSONDecodeError:
                            continue
                    if examples:
                        return examples
            except Exception:
                continue

        return []

    def get_example_count(self, ac_type="", test_type=""):
        self.initialize()
        if not ac_type and not test_type:
            return self._coll_tcs.count()
        try:
            where = {}
            if ac_type and test_type:
                where = {"$and": [{"ac_type": ac_type}, {"test_type": test_type}]}
            elif ac_type:
                where = {"ac_type": ac_type}
            else:
                where = {"test_type": test_type}
            return len(self._coll_tcs.get(where=where, include=[])["ids"])
        except Exception:
            return 0

    # ── Collection 3: Domain Vocabulary ──────────────────────────────────────

    def extract_and_store_vocab(self, requirements):
        """
        Extract and store screen + element names from all requirements.
        Returns count of vocabulary items stored.
        """
        self.initialize()
        docs, metas, ids = [], [], []
        seen_screens, seen_elems = set(), set()

        for req in requirements:
            vocab = _extract_vocab(req)
            for screen in vocab["screens"]:
                if screen in seen_screens:
                    continue
                seen_screens.add(screen)
                ids.append(f"vocab_s_{uuid.uuid4().hex[:8]}")
                docs.append(f"screen: {screen} | category: {vocab['category']} | {vocab['req_id']} {vocab['req_title']}")
                metas.append({"vocab_type":"screen","term":screen,
                               "category":vocab["category"],"req_id":vocab["req_id"]})
            for elem in vocab["elements"]:
                if elem in seen_elems:
                    continue
                seen_elems.add(elem)
                ids.append(f"vocab_e_{uuid.uuid4().hex[:8]}")
                docs.append(f"element: {elem} | category: {vocab['category']} | {vocab['req_id']} {vocab['req_title']}")
                metas.append({"vocab_type":"element","term":elem,
                               "category":vocab["category"],"req_id":vocab["req_id"]})

        if docs:
            self._coll_vocab.add(documents=docs, metadatas=metas, ids=ids)
            console.print(
                f"[green]Domain vocab:[/green] "
                f"{len(seen_screens)} screens, {len(seen_elems)} UI elements stored"
            )
        return len(docs)

    def lookup_component(self, category, req_title, ac_text="", n=3):
        """
        Dynamic component lookup — replaces hardcoded _COMPONENT_MAP.
        Returns best matching screen name or None.
        """
        self.initialize()
        if self._coll_vocab.count() == 0:
            return None
        query = f"{category} {req_title} {ac_text[:100]}"
        try:
            res = self._coll_vocab.query(
                query_texts=[query],
                n_results=min(n, self._coll_vocab.count()),
                where={"vocab_type": "screen"},
                include=["metadatas", "distances"],
            )
        except Exception:
            return None
        if not res["metadatas"] or not res["metadatas"][0]:
            return None
        term = res["metadatas"][0][0].get("term","")
        dist = res["distances"][0][0]
        if (1 - dist) > 0.25 and term:
            return term if term.lower().endswith("screen") else f"{term} Screen"
        return None

    def get_domain_vocab_summary(self, category=""):
        self.initialize()
        if self._coll_vocab.count() == 0:
            return {"screens":[], "elements":[]}
        try:
            kw = {"include": ["metadatas"]}
            if category:
                kw["where"] = {"category": category.lower()}
            res = self._coll_vocab.get(**kw)
            screens = [m["term"] for m in res["metadatas"] if m.get("vocab_type")=="screen"]
            elements = [m["term"] for m in res["metadatas"] if m.get("vocab_type")=="element"]
            return {"screens": list(set(screens)), "elements": list(set(elements))}
        except Exception:
            return {"screens":[], "elements":[]}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def get_all_requirements(self):
        self.initialize()
        if self._coll_reqs.count() == 0:
            return []
        r = self._coll_reqs.get(include=["documents","metadatas"])
        return [{"document":d,"metadata":m} for d,m in zip(r["documents"],r["metadatas"])]

    def clear(self):
        """Clear requirements + vocab. Preserves tc_examples (approved patterns)."""
        self.initialize()
        for name in [self.COLL_REQS, self.COLL_VOCAB]:
            self._client.delete_collection(name)
        for attr, name in [("_coll_reqs", self.COLL_REQS), ("_coll_vocab", self.COLL_VOCAB)]:
            kw = {"name": name}
            if self._embed_fn:
                kw["embedding_function"] = self._embed_fn
            try:
                coll = self._client.create_collection(**kw)
            except Exception:
                kw.pop("embedding_function", None)
                coll = self._client.create_collection(**kw)
            setattr(self, attr, coll)
        console.print("[yellow]ChromaDB cleared (requirements + vocab). Examples preserved.[/yellow]")

    def clear_all(self):
        """Wipe all 3 collections."""
        self.initialize()
        for name in [self.COLL_REQS, self.COLL_TCS, self.COLL_VOCAB]:
            self._client.delete_collection(name)
        self._ready = False
        self.initialize()
        console.print("[yellow]All ChromaDB collections cleared.[/yellow]")

    @property
    def stats(self):
        self.initialize()
        return {
            "requirements": self._coll_reqs.count(),
            "tc_examples":  self._coll_tcs.count(),
            "domain_vocab": self._coll_vocab.count(),
        }