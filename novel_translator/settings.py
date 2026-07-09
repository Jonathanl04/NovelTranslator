import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_DATA_DIR", ROOT / "data"))
OUTPUT_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_OUTPUT_ROOT", DATA_ROOT))
TRANSLATED_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_TRANSLATED_ROOT", DATA_ROOT))
CONFIG_PATH = Path(os.environ.get("NOVEL_TRANSLATOR_CONFIG_PATH", DATA_ROOT / "translator_config.json"))
GLOSSARY_PATH = Path(os.environ.get("NOVEL_TRANSLATOR_GLOSSARY_PATH", DATA_ROOT / "glossary.json"))
GLOSSARY_ROOT = Path(os.environ.get("NOVEL_TRANSLATOR_GLOSSARY_ROOT", DATA_ROOT))
FRONTEND_DIST = ROOT / "frontend" / "dist"
LLM_FAILURE_LOG = Path(os.environ.get("NOVEL_TRANSLATOR_FAILURE_LOG", DATA_ROOT / "logs" / "llm_failures.jsonl"))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL_PRESETS = [
    {"model": "deepseek/deepseek-v4-flash", "provider": "deepseek"},
    {"model": "deepseek/deepseek-v4-pro", "provider": "deepseek"},
    {"model": "xiaomi/mimo-v2.5", "provider": "xiaomi"},
    {"model": "xiaomi/mimo-v2.5-pro", "provider": "xiaomi"},
]
DEFAULT_TRANSLATION_MODEL = DEFAULT_MODEL_PRESETS[0]["model"]
DEFAULT_TRANSLATION_PROVIDER = DEFAULT_MODEL_PRESETS[0]["provider"]
DEFAULT_GLOSSARY_MODEL = DEFAULT_MODEL_PRESETS[0]["model"]
DEFAULT_GLOSSARY_PROVIDER = DEFAULT_MODEL_PRESETS[0]["provider"]
ALLOWED_GENDERS = {"", "male", "female", "it"}
