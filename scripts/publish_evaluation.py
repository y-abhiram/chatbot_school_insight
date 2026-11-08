import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from product.config import ROOT
from product.langsmith_eval import publish
parser=argparse.ArgumentParser();parser.add_argument('--report',default='docs/evaluation/acceptance-matrix.json');args=parser.parse_args()
# This explicit command publishes sample questions/results to the user's LangSmith workspace.
try:print(publish(json.loads((ROOT/args.report).read_text())))
except Exception as error:raise SystemExit('Publication failed ('+type(error).__name__+'). Configure your LangSmith workspace/API key locally. Local evaluation results are preserved.')
