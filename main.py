from libs.service_main import ServiceMain
from argparse import ArgumentParser


def main(**kwargs):
    app = ServiceMain()
    app.run(**kwargs)


if __name__ == '__main__':
    args = ArgumentParser()
    args.add_argument("-P", "--port", type=int, default=16001)
    parse = args.parse_args()
    port = parse.port

    try:
        port = int(port)
        if not 8000 < port < 65535:
            port = 16001
    except ValueError:
        port = 16001

    main(port=port)
