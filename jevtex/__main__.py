import uvicorn

uvicorn.run("jevtex.app:app", host="127.0.0.1", port=8765, access_log=False)
