import sys

from vhdl_tools.cli import main

main(["synth", *sys.argv[1:]])
