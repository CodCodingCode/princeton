"""UI helpers for the melanoma copilot Streamlit app.

Each submodule is imported lazily from ``app.py`` AFTER
``load_dotenv`` has run, so modules that touch ``neoantigen`` still
see the correct ``K2_BASE_URL`` / ``KIMI_API_KEY`` at module-import
time. Keep this file empty.
"""
