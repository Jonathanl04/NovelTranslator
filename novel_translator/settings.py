from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "output"
TRANSLATED_ROOT = ROOT / "translated"
CONFIG_PATH = ROOT / "translator_config.json"
GLOSSARY_PATH = ROOT / "glossary.json"
GLOSSARY_ROOT = ROOT / "glossaries"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_TRANSLATION_MODEL = "deepseek-v4-flash"
DEFAULT_GLOSSARY_MODEL = "deepseek-v4-flash"
MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}
ALLOWED_GENDERS = {"", "male", "female", "it"}
