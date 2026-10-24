import os
import tempfile

# Tests never download or load the real embedding model; the engine falls back to word overlap
# unless a test injects its own embedder. Models are read from an empty temp directory, so risk
# scoring uses the formula unless a test trains and saves one.
os.environ.setdefault("CIVICLOOP_EMBEDDINGS", "off")
os.environ.setdefault("CIVICLOOP_MODEL_DIR", tempfile.mkdtemp(prefix="civicloop-models-"))
