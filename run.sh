#!/bin/bash
cd /Users/mohammedthahers/cold-outreach
CMD=${1:-run}
/Users/mohammedthahers/cold-outreach/.venv/bin/python main.py "$CMD" >> /Users/mohammedthahers/cold-outreach/run.log 2>&1