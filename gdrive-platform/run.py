"""Tiny launcher — `python run.py`."""
import uvicorn

if __name__ == "__main__":
    # host=0.0.0.0 so other people on the LAN (or through a tunnel) can reach
    # this machine, not just localhost.
    # reload=False: auto-reload is a dev convenience (watches files, restarts
    # on save) and adds overhead + occasional flakiness. This server is meant
    # to stay up continuously for a team, so it's off here.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)