import uvicorn

from core.app import create_app
from core.config import get_settings

app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
