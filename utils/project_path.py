from os import path, mkdir

UTILS_PATH = path.dirname(path.abspath(__file__))
ROOT_PATH = path.dirname(UTILS_PATH)
DATA_PATH = path.join(ROOT_PATH, 'data')
CONFIG_PATH = path.join(ROOT_PATH, 'config')

if not path.exists(DATA_PATH): 
    mkdir(DATA_PATH)
    mkdir(path.join(DATA_PATH, 'databases'))
    mkdir(path.join(DATA_PATH, 'images'))
    mkdir(path.join(DATA_PATH, 'exports'))

if not path.exists(CONFIG_PATH): mkdir(CONFIG_PATH)

