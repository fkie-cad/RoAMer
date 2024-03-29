import argparse

from roamer.RoAMer import RoAMer
import importlib


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='RoAMer')
    parser.add_argument('Samples', metavar='Sample', type=str, help='Path to sample or folder of samples')
    parser.add_argument('--no-headless', action='store_false', help='Start the Sandbox in headless mode', dest="headless")
    parser.add_argument('--vm', action='store', help='This can be used to force a VM past the config-file', default="")
    parser.add_argument('--snapshot', action='store', help='This can be used to force a snapshot past the config-file', default="")
    parser.add_argument('--config', action='store', help="Which config shall be used?", default="config")
    parser.add_argument('--ident', action="store", help="Configure an identifier for the output.", default="")
    parser.add_argument('--output', action="store", help="Specify a custom output folder for the dumps", default=None)

    args = parser.parse_args()
    roamer = RoAMer(importlib.import_module(args.config), args.headless, args.vm, args.snapshot, args.ident)
    roamer.run(args.Samples, output_folder=args.output)
