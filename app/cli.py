"""Terminal chat for quick testing:  python -m app.cli"""
from pathlib import Path

from . import config
from .agent import RecommenderAgent
from .catalog import Catalog
from .diagnose import explain

BASE_DIR = Path(__file__).resolve().parent.parent


def main():
    for p in config.problems():
        print("Config warning:", p)
    agent = RecommenderAgent(Catalog(str(BASE_DIR / config.CATALOG_PATH)))
    messages: list = []
    print(f"Shopping assistant ({config.TOOL_MODE} mode). Type 'quit' to exit.\n")
    while True:
        text = input("You: ").strip()
        if text.lower() in {"quit", "exit"}:
            break
        if not text:
            continue
        checkpoint = len(messages)
        messages.append({"role": "user", "content": text})
        try:
            print("\nAssistant:", agent.run_turn(messages), "\n")
        except Exception as e:  # show a short, readable error instead of a traceback
            del messages[checkpoint:]
            print("\n[error]", explain(e))
            print("         Run: python -m app.diagnose\n")


if __name__ == "__main__":
    main()
