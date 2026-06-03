import uvicorn

from app.api import app
from app.core.config import settings


def main() -> None:
    uvicorn.run(app, host=settings.api_bind_host, port=settings.api_port)


if __name__ == "__main__":
    main()
