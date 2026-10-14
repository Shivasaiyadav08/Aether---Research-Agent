"""Configure process limits before importing Chroma and numerical libraries."""
import os

from app.core.memory import configure_process_memory_environment


def main():
    configure_process_memory_environment()
    # Report configuration mistakes before loading numerical/AI libraries.
    from app.core.readiness import check_production_configuration
    check_production_configuration()
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, workers=1)


if __name__ == "__main__":
    main()
