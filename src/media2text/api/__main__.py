"""Run API via python -m media2text.api."""

import uvicorn

from media2text.api.app import create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8765)
