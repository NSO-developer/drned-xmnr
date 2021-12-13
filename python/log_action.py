#!/usr/bin/env python

import sys
from argparse import ArgumentParser

import ncs
from ncs.dp import Action, Daemon


class LogAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output):
        sys.stdout.write(f'{input.device}: {input.message}')


if __name__ == '__main__':
    ap = ArgumentParser()
    ap.add_argument('-i', '--ip', type=str, default='127.0.0.1')
    ap.add_argument('-p', '--port', type=int, default=ncs.PORT)
    args = ap.parse_args()
    d = Daemon(name='clilogger', ip=args.ip, port=args.port)
    action = LogAction(daemon=d, actionpoint='xmnr-cli-log')
    d.start()
    print('logger started, hit <ENTER> to quit\n')
    sys.stdin.read(1)
    d.finish()
