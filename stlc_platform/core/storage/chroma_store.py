"""
ChromaDB Vector Store (migrated)
================================
Three collections: requirements, tc_examples, domain_vocab.

Import path change:
  Old: from chroma_store import RequirementsVectorStore
  New: from stlc_platform.core.storage import RequirementsVectorStore

No logic changes from original — only import paths updated.
"""

import hashlib
import json
import logging
import os
import re
import uuid
import warnings
from datetime import datetime, timezone

import requests

warnings.filterwarnings("ignore", category=DeprecationWarning, module="chromadb")
warnings.filterwarnings("ignore", message=".*pydantic.*", category=UserWarning)
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("onnxruntime").setLevel(logging.ERROR)

from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)


# ── client factory ───────────────────────────────────────────────────────────


def _make_client(path):
    """
    Create a ChromaDB PersistentClient.
    Temporarily clears env vars to avoid pydantic-settings ValidationError.

    Uses mkdtemp() + manual cleanup instead of TemporaryDirectory() context
    manager to avoid WinError 32 on Windows: the context manager's __exit__
    tries to delete the temp dir while ChromaDB still holds a lock on an
    SQLite file inside it.
    """
    import shutil
    import tempfile

    try:
        from dotenv import dotenv_values

        _dot_env_keys = set(dotenv_values().keys())
    except (ImportError, OSError):
        _dot_env_keys = set()

    _saved_env = {k: os.environ.pop(k) for k in _dot_env_keys if k in os.environ}
    _orig_cwd = os.getcwd()
    _tmpdir = tempfile.mkdtemp()

    try:
        os.chdir(_tmpdir)
        try:
            import chromadb

            abs_path = path if os.path.isabs(path) else os.path.join(_orig_cwd, path)
            _settings = chromadb.Settings(
                is_persistent=True,
                persist_directory=abs_path,
                allow_reset=True,
                anonymized_telemetry=False,
            )
        finally:
            os.chdir(_orig_cwd)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Could not create ChromaDB PersistentClient at '{path}': {e}\n"
            "Try: pip install --upgrade 'chromadb>=0.5.3'"
        ) from e
    finally:
        os.environ.update(_saved_env)
        # Best-effort cleanup — ignore errors (Windows may still hold a lock)
        shutil.rmtree(_tmpdir, ignore_errors=True)

    try:
        return chromadb.Client(_settings)
    except Exception as e:
        raise RuntimeError(
            f"Could not create ChromaDB PersistentClient at '{path}': {e}\n"
            "Try: pip install --upgrade 'chromadb>=0.5.3'"
        ) from e


# ── embedding ────────────────────────────────────────────────────────────────


def _ollama_ok(model, url):
    try:
        tags = requests.get(url.replace("/api/embeddings", "/api/tags"), timeout=5)
        if tags.status_code != 200:
            return False
        base = model.split(":")[0]
        return any(
            m == model or m.startswith(base + ":")
            for m in [m["name"] for m in tags.json().get("models", [])]
        )
    except Exception:
        return False


def _ollama_live(model, url):
    try:
        r = requests.post(url, json={"model": model, "prompt": "test"}, timeout=30)
        return r.status_code == 200 and "embedding" in r.json()
    except Exception:
        return False


def _best_embedding_fn(chromadb_config):
    from chromadb.utils import embedding_functions as ef

    cfg = chromadb_config
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
        console.print(
            f"[green]Embedding:[/green] SentenceTransformer / {cfg.sentence_transformer_model}"
        )
        return fn
    except (ImportError, RuntimeError, OSError):
        pass
    try:
        fn = ef.DefaultEmbeddingFunction()
        console.print("[green]Embedding:[/green] DefaultEmbeddingFunction (ONNX MiniLM)")
        return fn
    except (ImportError, RuntimeError, OSError):
        pass
    console.print("[yellow]No embedding function — ChromaDB using internal default[/yellow]")
    return None


# ── domain vocabulary extractor ──────────────────────────────────────────────

_SCREEN_RE = [
    r"\b([A-Z][a-zA-Z\s]{2,35})\s+(?:screen|page|view|panel|modal|dialog|form|overlay)\b",
    r"\b([A-Z][a-zA-Z\s]{2,30})\s+Screen\b",
    r"(?:navigates?\s+to|opens?\s+the|launches?\s+the|displays?\s+the)\s+([A-Z][a-zA-Z\s]{2,35})",
]
_ELEM_RE = [
    r"['\"]([A-Za-z][A-Za-z\s\-]{1,25})['\"]",
    r"\b([A-Z][a-zA-Z\s]{1,20})\s+(?:button|field|label|input|toggle|checkbox|dropdown|link|tab)\b",
]
_SKIP_WORDS = {
    "the",
    "this",
    "that",
    "each",
    "every",
    "any",
    "all",
    "customer",
    "user",
    "system",
    "app",
}


def _extract_vocab(req):
    """Extract screen and element names from a requirement object."""
    ac_list = []
    if hasattr(req, "acceptance_criteria"):
        ac_list = req.acceptance_criteria or []

    text = " ".join([req.title, req.description] + ac_list)
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
        "screens": list(screens),
        "elements": list(elements),
        "category": (getattr(req, "category", "") or req.req_id).lower(),
        "req_id": req.req_id,
        "req_title": req.title,
    }


# ── TC example formatter ────────────────────────────────────────────────────


def _tc_to_doc(tc):
    steps = ""
    for i, s in enumerate(tc.get("steps", []), 1):
        a = s.get("action", "") if isinstance(s, dict) else str(s)
        r = s.get("expected_result", "") if isinstance(s, dict) else ""
        steps += f"  {i}. {a} -> {r}\n"
    return (
        f"title: {tc.get('title', '')}\n"
        f"test_type: {tc.get('test_type', '')}\n"
        f"ac_type: {tc.get('ac_type', '')}\n"
        f"description: {tc.get('description', '')}\n"
        f"preconditions: {tc.get('preconditions', '')}\n"
        f"given: {tc.get('given', '')}\n"
        f"when: {tc.get('when', '')}\n"
        f"then: {tc.get('then', '')}\n"
        f"steps:\n{steps}"
        f"expected_outcome: {tc.get('expected_outcome', '')}\n"
        f"component: {tc.get('component', '')}\n"
    )


# ── Vector store ─────────────────────────────────────────────────────────────


class RequirementsVectorStore:
    COLL_REQS = "requirements"
    COLL_TCS = "tc_examples"
    COLL_VOCAB = "domain_vocab"

    def __init__(self, chromadb_config=None, project_id="default"):
        self._config = chromadb_config
        self._project_id = str(project_id or "default")
        self._client = self._embed_fn = None
        self._coll_reqs = self._coll_tcs = self._coll_vocab = None
        self._ready = False

    def _get_config(self):
        # If config is a raw dict it cannot be used directly (attribute access will fail).
        # Fall back to the global config_loader which always returns a proper config object.
        if self._config is not None and not isinstance(self._config, dict):
            return self._config
        from stlc_platform.core.config_loader import config

        return config.chromadb

    def initialize(self):
        if self._ready:
            return
        try:
            cfg = self._get_config()
            console.print("[cyan]Initialising ChromaDB (3 collections)...[/cyan]")
            os.makedirs(cfg.persist_directory, exist_ok=True)
            self._client = _make_client(cfg.persist_directory)
            self._embed_fn = _best_embedding_fn(cfg)

            def _gc(name):
                kw = {"name": name, "metadata": {"hnsw:space": "cosine"}}
                if self._embed_fn:
                    kw["embedding_function"] = self._embed_fn
                try:
                    return self._client.get_or_create_collection(**kw)
                except Exception as exc:
                    err = str(exc).lower()
                    if "embedding function" in err or "conflict" in err:
                        # Persisted collection has a different embedding function.
                        # Delete the stale collection and recreate with the current
                        # embedding function so embeddings are consistent.
                        logger.warning(
                            "Embedding function conflict on collection '%s' — "
                            "deleting stale collection and recreating with current embedding function.",
                            name,
                        )
                        try:
                            self._client.delete_collection(name)
                        except Exception as del_exc:
                            logger.debug("Could not delete stale collection '%s': %s", name, del_exc)
                        return self._client.get_or_create_collection(**kw)
                    kw.pop("metadata", None)
                    return self._client.get_or_create_collection(**kw)

            self._coll_reqs = _gc(self.COLL_REQS)
            self._coll_tcs = _gc(self.COLL_TCS)
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

    # ── Collection 1: Requirements ───────────────────────────────────────────

    def add_requirements(self, requirements):
        self.initialize()
        if not requirements:
            return
        docs, metas, ids = [], [], []
        for req in requirements:
            document = req.to_chroma_document()
            content_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()[:16]
            safe_project = re.sub(r"[^a-zA-Z0-9_-]", "_", self._project_id)
            safe_req_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(req.req_id))
            revision_id = f"requirement_{safe_project}_{safe_req_id}_{content_hash}"
            revision_number, previous_revision_id = self._next_revision(req.req_id, content_hash)
            ids.append(revision_id)
            docs.append(document)
            metas.append(
                {
                    "project_id": self._project_id,
                    "req_id": req.req_id,
                    "title": req.title,
                    "priority": req.priority,
                    "category": getattr(req, "category", "Functional"),
                    "tags": ",".join(getattr(req, "tags", []) or []),
                    "content_hash": content_hash,
                    "revision_id": revision_id,
                    "revision_number": revision_number,
                    "previous_revision_id": previous_revision_id,
                    "lineage_key": f"{self._project_id}:{req.req_id}",
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        self._coll_reqs.upsert(documents=docs, metadatas=metas, ids=ids)
        console.print(f"[green]Indexed {len(requirements)} requirement(s)[/green]")

    def _next_revision(self, req_id, content_hash):
        """Return lineage metadata while making identical indexing idempotent."""
        try:
            existing = self._coll_reqs.get(
                where={
                    "$and": [
                        {"project_id": self._project_id},
                        {"req_id": str(req_id)},
                    ]
                },
                include=["metadatas"],
            )
            metadatas = existing.get("metadatas", []) or []
        except (AttributeError, TypeError, ValueError):
            metadatas = []
        if not isinstance(metadatas, list):
            metadatas = []
        for metadata in metadatas:
            if metadata.get("content_hash") == content_hash:
                return int(metadata.get("revision_number", 1)), str(
                    metadata.get("previous_revision_id", "")
                )
        if not metadatas:
            return 1, ""
        latest = max(metadatas, key=lambda item: int(item.get("revision_number", 0)))
        return int(latest.get("revision_number", 0)) + 1, str(latest.get("revision_id", ""))

    def search_similar(self, query, n_results=3, filter_metadata=None, min_similarity=0.3):
        self.initialize()
        count = self._coll_reqs.count()
        if count == 0:
            return []
        kw = {
            "query_texts": [query],
            "n_results": min(n_results, count),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter_metadata:
            kw["where"] = filter_metadata
        else:
            kw["where"] = {"project_id": self._project_id}
        res = self._coll_reqs.query(**kw)
        if not res["documents"] or not res["documents"][0]:
            return []
        results = []
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            score = round(1 - dist, 4)
            if score >= min_similarity:
                results.append(
                    {
                        "document": d,
                        "metadata": m,
                        "similarity_score": score,
                    }
                )
            else:
                logger.debug(
                    "search_similar: filtered out result (score=%.4f < threshold=%.2f)",
                    score,
                    min_similarity,
                )
        return results

    def get_context_for_requirement(self, requirement):
        similar = self.search_similar(
            requirement.to_chroma_document(),
            n_results=3,
            min_similarity=0.3,
        )
        lines = []
        for item in similar:
            m = item["metadata"]
            lines.append(f"- [{m['req_id']}] {m['title']} (similarity: {item['similarity_score']})")
        return "\n".join(lines) if lines else ""

    # ── Collection 2: TC Examples ────────────────────────────────────────────

    def store_approved_tc(self, tc_dict, ac_type, test_type, domain="", human_approved=False):
        if not human_approved:
            raise ValueError("RAG promotion requires explicit human approval")
        self.initialize()
        tc_dict = dict(tc_dict)
        tc_dict.update({"ac_type": ac_type, "test_type": test_type, "domain": domain})
        canonical = json.dumps(tc_dict, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        doc_id = f"ex_{ac_type}_{test_type}_{content_hash}"
        meta = {
            "ac_type": ac_type,
            "test_type": test_type,
            "domain": domain,
            "title": tc_dict.get("title", "")[:120],
            "component": tc_dict.get("component", ""),
            "tc_json": json.dumps(tc_dict, ensure_ascii=False)[:3000],
            "human_approved": True,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": content_hash,
        }
        self._coll_tcs.upsert(documents=[_tc_to_doc(tc_dict)], metadatas=[meta], ids=[doc_id])
        console.print(f"[green]Stored example TC:[/green] {doc_id} ({ac_type}/{test_type})")
        return doc_id

    def delete_approved_tc(self, doc_id):
        """Remove a promoted example after an explicit human reversal."""
        if not doc_id:
            return
        self.initialize()
        self._coll_tcs.delete(ids=[doc_id])
        console.print(f"[yellow]Removed approved example TC:[/yellow] {doc_id}")

    @staticmethod
    def _parse_query_results(res, min_similarity):
        """Extract valid examples from a ChromaDB query result."""
        if not res["documents"] or not res["documents"][0]:
            return []
        examples = []
        for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
            tj = meta.get("tc_json", "")
            if not tj:
                continue
            score = round(1 - dist, 4)
            if score < min_similarity:
                logger.debug(
                    "retrieve_examples: filtered out example (score=%.4f < threshold=%.2f)",
                    score,
                    min_similarity,
                )
                continue
            try:
                tc = json.loads(tj)
                tc["_similarity"] = score
                examples.append(tc)
            except json.JSONDecodeError:
                continue
        return examples

    def retrieve_examples(self, ac_text, ac_type, test_type, n=2, min_similarity=0.4):
        self.initialize()
        count = self._coll_tcs.count()
        if count == 0:
            return []

        query = f"{ac_type} {test_type} {ac_text[:200]}"

        for where in [
            {"$and": [{"ac_type": ac_type}, {"test_type": test_type}]},
            {"ac_type": ac_type},
            None,
        ]:
            try:
                kw = {
                    "query_texts": [query],
                    "n_results": min(n, count),
                    "include": ["metadatas", "distances"],
                }
                if where:
                    kw["where"] = where
                res = self._coll_tcs.query(**kw)
                examples = self._parse_query_results(res, min_similarity)
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
                docs.append(
                    f"screen: {screen} | category: {vocab['category']} "
                    f"| {vocab['req_id']} {vocab['req_title']}"
                )
                metas.append(
                    {
                        "vocab_type": "screen",
                        "term": screen,
                        "category": vocab["category"],
                        "req_id": vocab["req_id"],
                    }
                )
            for elem in vocab["elements"]:
                if elem in seen_elems:
                    continue
                seen_elems.add(elem)
                ids.append(f"vocab_e_{uuid.uuid4().hex[:8]}")
                docs.append(
                    f"element: {elem} | category: {vocab['category']} "
                    f"| {vocab['req_id']} {vocab['req_title']}"
                )
                metas.append(
                    {
                        "vocab_type": "element",
                        "term": elem,
                        "category": vocab["category"],
                        "req_id": vocab["req_id"],
                    }
                )

        if docs:
            self._coll_vocab.add(documents=docs, metadatas=metas, ids=ids)
            console.print(
                f"[green]Domain vocab:[/green] "
                f"{len(seen_screens)} screens, {len(seen_elems)} UI elements stored"
            )
        return len(docs)

    def lookup_component(self, category, req_title, ac_text="", n=3):
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
        term = res["metadatas"][0][0].get("term", "")
        dist = res["distances"][0][0]
        if (1 - dist) > 0.25 and term:
            return term if term.lower().endswith("screen") else f"{term} Screen"
        return None

    def add_vocab(self, terms: list, domain: str = "") -> int:
        """Add domain vocabulary terms to the domain_vocab collection.

        Args:
            terms: List of vocabulary terms to add (component names, UI elements, etc.)
            domain: Optional domain label.

        Returns:
            Number of new terms added (skips duplicates via upsert).
        """
        self.initialize()
        if not terms:
            return 0
        docs, metas, ids = [], [], []
        for term in terms:
            term = term.strip()
            if not term:
                continue
            safe = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")
            doc_id = f"vocab_auto_{safe}"
            ids.append(doc_id)
            docs.append(f"term: {term} | domain: {domain}")
            metas.append(
                {
                    "vocab_type": "auto_term",
                    "term": term,
                    "domain": domain,
                    "source": "auto_extracted",
                }
            )
        if not docs:
            return 0
        self._coll_vocab.upsert(documents=docs, metadatas=metas, ids=ids)
        return len(docs)

    def get_domain_vocab_summary(self, category=""):
        self.initialize()
        if self._coll_vocab.count() == 0:
            return {"screens": [], "elements": []}
        try:
            kw = {"include": ["metadatas"]}
            if category:
                kw["where"] = {"category": category.lower()}
            res = self._coll_vocab.get(**kw)
            screens = [m["term"] for m in res["metadatas"] if m.get("vocab_type") == "screen"]
            elements = [m["term"] for m in res["metadatas"] if m.get("vocab_type") == "element"]
            return {"screens": list(set(screens)), "elements": list(set(elements))}
        except Exception:
            return {"screens": [], "elements": []}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def get_all_requirements(self):
        self.initialize()
        if self._coll_reqs.count() == 0:
            return []
        r = self._coll_reqs.get(include=["documents", "metadatas"])
        return [{"document": d, "metadata": m} for d, m in zip(r["documents"], r["metadatas"])]

    def clear(self):
        self.initialize()
        for name in [self.COLL_REQS, self.COLL_VOCAB]:
            self._client.delete_collection(name)
        for attr, name in [
            ("_coll_reqs", self.COLL_REQS),
            ("_coll_vocab", self.COLL_VOCAB),
        ]:
            kw = {"name": name}
            if self._embed_fn:
                kw["embedding_function"] = self._embed_fn
            try:
                coll = self._client.create_collection(**kw)
            except Exception:
                kw.pop("embedding_function", None)
                coll = self._client.create_collection(**kw)
            setattr(self, attr, coll)
        console.print(
            "[yellow]ChromaDB cleared (requirements + vocab). Examples preserved.[/yellow]"
        )

    def clear_all(self):
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
            "tc_examples": self._coll_tcs.count(),
            "domain_vocab": self._coll_vocab.count(),
        }
