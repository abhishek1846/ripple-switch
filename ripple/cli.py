import argparse
import getpass
import json
import sys
from pathlib import Path

from .core import AREAS, Ripple, RippleError


def main(argv=None):
    parser = argparse.ArgumentParser(description='Ripple: one change across application, documentation, and reporting.')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    switch_test = commands.add_parser('switch-test')
    switch_register = commands.add_parser('switch-register')
    switch_register.add_argument('--server', required=True)
    switch_register.add_argument('--room', required=True)
    switch_register.add_argument('--room-url', default='')
    start = commands.add_parser('start')
    start.add_argument('--request', required=True)
    start.add_argument('--plan', choices=['basic', 'pro'], default='basic')
    start.add_argument('--limit', type=int, default=10)
    for name in ['inspect', 'propose', 'apply']:
        command = commands.add_parser(name)
        command.add_argument('change')
        command.add_argument('area', choices=list(AREAS))
        command.add_argument('--actor')
        if name == 'inspect':
            command.add_argument('--room-url')
        if name == 'propose':
            command.add_argument('--patch', type=Path, required=True)
            command.add_argument('--summary', required=True)
    check = commands.add_parser('check')
    check.add_argument('change')
    export = commands.add_parser('export')
    export.add_argument('--output', type=Path, required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--port', type=int, default=8790)
    args = parser.parse_args(argv)
    app = Ripple(args.root)
    try:
        if args.command == 'status':
            result = app.status()
        elif args.command == 'switch-test':
            from .switch import Switch
            result = Switch(app).test()
        elif args.command == 'switch-register':
            from .switch import Switch
            key = getpass.getpass('Switch registration key (hidden, not saved): ')
            result = Switch(app).register(args.server, key, args.room, args.room_url)
        elif args.command == 'start':
            result = app.start(args.request, args.plan, args.limit)
        elif args.command == 'inspect':
            result = app.inspect(args.change, args.area, args.actor, args.room_url)
        elif args.command == 'propose':
            result = app.propose(args.change, args.area, json.loads(args.patch.read_text()), args.summary, args.actor)
        elif args.command == 'apply':
            result = app.apply(args.change, args.area, args.actor)
        elif args.command == 'check':
            result = app.check(args.change)
        elif args.command == 'export':
            result = app.status()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2))
            result = {'saved': str(args.output)}
        elif args.command == 'serve':
            from .server import serve
            serve(app, args.port)
            return
        print(json.dumps(result, indent=2))
    except (RippleError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        sys.exit(1)
