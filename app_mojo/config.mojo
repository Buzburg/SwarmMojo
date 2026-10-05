"""ROMS Mojo Configuration and Singleton Model Loader.

Hard-partitioned for local LLM co-location:
- Zero GPU VRAM consumption (pinned to CPU)
- Thread capping to prevent host CPU core starvation
- Context window budgeting for compact prompt prefill
"""

from std.python import Python, PythonObject

struct ROMSConfig:
    var embedding_model: String
    var embedding_dim: Int
    var max_concurrent: Int
    var max_cpu_percent: Float64
    var min_ram_mb: Float64
    var tool_timeout: Float64
    var max_rag_chars: Int

    def __init__(out self):
        self.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        self.embedding_dim = 384
        self.max_concurrent = 2
        self.max_cpu_percent = 85.0
        self.min_ram_mb = 2048.0
        self.tool_timeout = 120.0
        self.max_rag_chars = 2000

def get_embedding_model() raises -> PythonObject:
    """Returns a SentenceTransformer model instance pinned to CPU to preserve GPU VRAM for local LLMs."""
    var torch = Python.import_module("torch")
    # Limit background CPU threads to 2 so model inference threads stay responsive
    torch.set_num_threads(2)

    var st = Python.import_module("sentence_transformers")
    var cfg = ROMSConfig()
    # Explicitly enforce device="cpu" to never allocate CUDA/OptiX VRAM
    return st.SentenceTransformer(cfg.embedding_model, device="cpu")

def get_base_paths() raises -> PythonObject:
    """Use the same configured directories as the Python tools and gateway."""
    var config = Python.import_module("app.config")
    var paths = Python.evaluate("[]")
    paths.append(config.DATA_DIR)
    paths.append(config.DB_PATH)
    paths.append(config.KNOWLEDGE_DIR)
    paths.append(config.SKILLS_DIR)
    paths.append(config.WORKSPACES_DIR)
    return paths
