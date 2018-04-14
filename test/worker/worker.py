from runner import Runner
import strategy.listen
import logging
import os
import random
import net

script_dir = os.path.dirname(os.path.realpath(__file__))

CONFIG_DIR = os.environ.get("CONFIG_DIR", os.path.join(script_dir, 'configs'))
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

_levelnum = getattr(logging, LOG_LEVEL.upper(), None)
if not isinstance(_levelnum, int):
    raise ValueError('Invalid log level: {}'.format(LOG_LEVEL))

logging.basicConfig(level=_levelnum, format="[%(levelname)s %(asctime)s] %(message)s", datefmt="%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

def load_config():
    filenames = os.listdir(CONFIG_DIR)
    return os.path.join(CONFIG_DIR, random.choice(filenames))

def load_strategy():
    return strategy.listen.PassiveStrategy()

if __name__ == "__main__":
    while True:
        # Get the config and strategy
        config = load_config
        strategy = load_strategy

        runner = Runner(load_config())
        runner.execute(load_strategy())
