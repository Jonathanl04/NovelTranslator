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
DEEPSEEK_FAILURE_LOG = Path(
    os.environ.get("NOVEL_TRANSLATOR_FAILURE_LOG", DATA_ROOT / "logs" / "deepseek_failures.jsonl")
)
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_TRANSLATION_MODEL = "deepseek-v4-flash"
DEFAULT_GLOSSARY_MODEL = "deepseek-v4-flash"
MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
ALLOWED_GENDERS = {"", "male", "female", "it"}
