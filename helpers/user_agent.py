"""User-Agent sent to data.gouv.fr services for identification and support."""

# Version statique pour éviter les erreurs de PackageNotFoundError sur Streamlit Cloud
__version__ = "1.0.0-web"
USER_AGENT = f"datagouv-prospector-web/{__version__}"
