"""
Single entrypoint for the migration pipeline.

Usage:
    python main.py run                     # start a new migration run
    python main.py resume <thread_id>      # resume a run paused at human_review_gate
    python main.py review                  # launch the CLI review queue directly
"""
import argparse
import sys

from workflow.langgraph_orchestrator import run_pipeline, resume_pipeline
from review.cli_review import run_review_queue


def main():
    parser = argparse.ArgumentParser(description="AI-assisted legacy migration pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Start a new migration run")

    resume_parser = sub.add_parser("resume", help="Resume a paused run")
    resume_parser.add_argument("thread_id", help="run_id printed when the pipeline paused")

    sub.add_parser("review", help="Open the human review queue for the current mappings.json")

    args = parser.parse_args()

    if args.command == "run":
        result = run_pipeline()
        if result["status"] == "paused":
            print("\nNext step:")
            print("  1. python main.py review")
            print(f"  2. python main.py resume {result['run_id']}")
    elif args.command == "resume":
        resume_pipeline(args.thread_id)
    elif args.command == "review":
        run_review_queue()


if __name__ == "__main__":
    sys.exit(main())
