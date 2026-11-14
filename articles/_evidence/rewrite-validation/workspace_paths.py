from pathlib import Path
import argparse
parser = argparse.ArgumentParser(description="Reproduce the scoped report experiments")
parser.add_argument("--workspace", type=Path, required=True,
                    help="Root containing the documented repos/ and outputs/ inputs")
WORKSPACE = parser.parse_args().workspace.resolve()
