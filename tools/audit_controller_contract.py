"""Read a PID method's source digest without importing model code or weights."""
import argparse
import ast
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    args=parser.parse_args()
    text=args.source.read_text()
    nodes=[node for node in ast.walk(ast.parse(text)) if isinstance(node,ast.FunctionDef) and node.name=='control_pid']
    if len(nodes)!=1:raise ValueError('Expected one control_pid function')
    node=nodes[0]
    source=''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno]).rstrip('\n')+'\n'
    print(json.dumps({'path':str(args.source),'line':node.lineno,
                      'sha256':hashlib.sha256(source.encode()).hexdigest()}))


if __name__=='__main__':main()
