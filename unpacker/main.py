import argparse
import logging
import os

from unpacker.Orchestrator import Orchestrator
from utility.win_env import get_user_path

import sys
# For utility imports
sys.path.append('..')

def main():
    logging.basicConfig(filename=os.path.join([get_user_path(), "roamer.log"]),
                        format="%(asctime)-15s %(levelname)-7s %(module)s.%(funcName)s(): %(message)s",
                        level=logging.DEBUG)

    parser = argparse.ArgumentParser(description='RoAMer Unpacker Module.')
    parser.add_argument('--local', action='store_true', help='Run the unpacker locally and store to disk instead of using network transmission.')
    args = parser.parse_args()
    orchestrator = Orchestrator()
    orchestrator.set_local_unpacker(args.local)
    orchestrator.run()


if __name__ == '__main__':
    main()
