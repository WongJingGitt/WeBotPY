import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))


def main(**kwargs):
    """
    开始Flask服务，接受的参数与flask的run函数相同。
    :param kwargs:
    :return:
    """
    from webot.services.service_main import ServiceMain
    app = ServiceMain()
    app.run(**kwargs)


def command_runner():
    from argparse import ArgumentParser
    args = ArgumentParser()
    args.add_argument("-P", "--port", type=int, default=16001, help="Web服务的端口号，默认16001")
    parse = args.parse_args()
    port = parse.port

    try:
        port = int(port)
        if not 8000 < port < 65535:
            port = 16001
    except ValueError:
        print("\033[1;33m输入的端口不在可用端口范围内(8000 - 65535)，将使用默认端口16001启动服务。\033[0m")
        port = 16001

    main(port=port)


if __name__ == "__main__":
    command_runner()
