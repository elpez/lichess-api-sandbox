#!/usr/bin/env python3
"""An interactive script to play with the Lichess API.

Docs for the API can be found at https://github.com/ornicar/lila#http-api
"""
# stdlib modules
import time
import argparse
import readline
import textwrap
import shutil
import sys
import os
from collections import Counter, namedtuple
from typing import List, Dict, Optional, Tuple, Iterable

# third-party modules
import chess

# my modules
from loadgames import fetch_all_games, print_verbose
from openings import OPENING_NAMES


DEFAULT_CACHE_DIR = '.lichess_cache'


def filter_by_move_prefix(games: List[dict], moves_so_far: List[str]) -> Iterable[dict]:
    """Return an iterator over all games that began with the given moves."""
    return (game for game in games if game['moves'][:len(moves_so_far)] == moves_so_far)


class MoveTree:
    def __init__(self) -> None:
        self.parent = None  # type: Optional[MoveTree]
        self.children = {}  # type: Dict[str, MoveTree]
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.total = 0
        self.stack = []  # type: List[str]

    @classmethod
    def from_parent(cls, parent: 'MoveTree', move: str) -> 'MoveTree':
        ret = cls()
        ret.parent = parent
        ret.stack = parent.stack + [move]
        return ret

    def build_next_level(self, games: List[dict]) -> None:
        if len(self.children) > 0:
            # The next level has already been built.
            return
        for game in games:
            if len(game['moves']) < len(self.stack) + 1:
                continue
            move = game['moves'][len(self.stack)]
            try:
                node = self.children[move]
            except KeyError:
                node = MoveTree.from_parent(self, move)
                self.children[move] = node
            node.total += 1
            if game['user_result'] == 'draw':
                node.draws += 1
            elif game['user_result'] == 'win':
                node.wins += 1
            else:
                node.losses += 1


class MoveExplorer:
    """Explore the moves made in a set of games (assumed to be from the same player)."""

    def __init__(self, games: List[dict], color: bool) -> None:
        self.all_games = games
        self.reset(color)

    def reset(self, color: bool = None) -> None:
        self.color = color if color is not None else self.color  # type: bool
        self.opening = None  # type: Optional[str]
        # The ply at which the opening was determined. Used for backtracking.
        self.opening_ply = 0
        self.tree = MoveTree()
        self.games = [g for g in self.all_games if g['user_color'] == self.color]
        self.tree.build_next_level(self.games)
        self.board = chess.Board()

    def backtrack(self) -> None:
        if self.tree.parent is not None:
            self.tree = self.tree.parent
            self.games = [g for g in filter_by_move_prefix(self.all_games, self.tree.stack)
                                  if g['user_color'] == self.color]
            self.board.pop()
            if len(self.tree.stack) <= self.opening_ply:
                self.opening = OPENING_NAMES.get(tuple(self.tree.stack))
                if self.opening is None:
                    self.opening_ply = 0

    def advance(self, move) -> None:
        try:
            self.tree = self.tree.children[move]
        except KeyError:
            raise ValueError from None
        else:
            self.games = [g for g in self.games
                                  if g['moves'][:len(self.tree.stack)] == self.tree.stack]
            self.board.push_san(move)
            try:
                self.opening = OPENING_NAMES[tuple(self.tree.stack)]
            except KeyError:
                pass
            else:
                self.opening_ply = len(self.tree.stack)
            self.tree.build_next_level(self.games)

    def flip(self) -> None:
        self.reset(not self.color)

    def moves_so_far(self) -> List[str]:
        return self.tree.stack

    def available_moves(self) -> List[Tuple[str, MoveTree]]:
        return sorted(self.tree.children.items(), key=lambda p: p[1].total, reverse=True)

    def your_turn(self) -> bool:
        return (self.color and len(self.tree.stack) % 2 == 0) or \
               (not self.color and len(self.tree.stack) % 2 == 1)

    def print_stats(self) -> None:
        if self.your_turn():
            print(format_pl('\nYOUR MOVES (from {} game{})', len(self.games)))
        else:
            print(format_pl("\nYOUR OPPONENTS' MOVES (from {} game{})", len(self.games)))
        for move, node in self.available_moves():
            wins = node.wins / node.total
            draws = node.draws / node.total
            losses = node.losses / node.total
            print('{}.'.format((len(self.tree.stack) // 2) + 1), end='')
            if len(self.tree.stack) % 2 == 1:
                print('..', end='')
            else:
                print(' ', end='')
            # I believe that Ng3xe5+ (7 chars) is the longest possible chess move in strict
            # algebraic notation.
            print('{:7}'.format(move), end='')
            print(' (you won {:6,.1%}, lost {:6,.1%},'.format(wins, losses), end='')
            print(' and drew {:6,.1%}'.format(draws), end='')
            print(format_pl(', from {} game{})', node.total))
        print()
        # Print the moves so far.
        moves_so_far = self.moves_so_far()
        if moves_so_far:
            columns = shutil.get_terminal_size()[0]
            remaining_columns = columns
            for move in self._move_str_helper(moves_so_far):
                if len(move) <= remaining_columns:
                    print(move, end='')
                    remaining_columns -= len(move)
                else:
                    print('\n' + move, end='')
                    remaining_columns = columns - len(move)
            # Print the name of the opening.
            if self.opening is not None:
                if len(self.opening) + 2 > remaining_columns:
                    print()
                print('({})'.format(self.opening))
            else:
                print()

    def _move_str_helper(self, moves_so_far):
        i = 0
        while i < len(moves_so_far) - 1:
            yield str(i//2+1) + '. ' + moves_so_far[i] + ' ' + moves_so_far[i+1] + '  '
            i += 2
        if i == len(moves_so_far) - 1:
            yield str(i//2+1) + '. ' + moves_so_far[i] + '  '


def format_pl(string: str, n: int) -> str:
    """Given a string with exactly two '{}' sequences, replace the first with `n` and the second
    with nothing if `n` is equal to 1 and 's' otherwise.
    """
    return string.format(n, '' if n == 1 else 's')


def input_yes_no(*args, **kwargs) -> bool:
    """Continually prompt the user (`args` and `kwargs` are passed to `input` unchanged) until
    they enter something that, after stripping whitespace, starts with a 'y' or an 'n'. Return
    True if it starts with a 'y', False if it starts with an 'n'.
    """
    while True:
        response = input(*args, **kwargs).strip().lower()
        if response.startswith('y'):
            return True
        elif response.startswith('n'):
            return False


# The config object represents the user configuration supplied as command-line arguments. We could
# just use the argparse.args object instead, but it's nice to uncouple the configuration from its
# implementation with argparse.
Config = namedtuple('Config', 'username speeds months exclude_computer refresh_cache verbose '
                              'cachedir')


def run_session(config) -> None:
    """Interact with the move tree in a terminal session."""
    if config.username is not None:
        username = config.username
    else:
        username = input('Please enter your Lichess username: ').strip()

    if config.cachedir and not os.path.exists(config.cachedir):
        print_verbose('Creating cache directory ' + config.cachedir, config=config)
        os.mkdir(config.cachedir)

    # Get the games and fire up the move explorer.
    print('\nLoading user data...\n')
    games = fetch_all_games(username, config=config)
    explorer = MoveExplorer(games, True)
    explorer.print_stats()

    # Run the REPL.
    while True:
        while True:
            # Continue reading until a non-blank line is entered.
            command = input('{}>>> '.format('white' if explorer.color else 'black')).strip()
            if command:
                break
        if command.lower() in ('quit', 'exit'):
            break
        else:
            handle_command(explorer, command)


def handle_command(explorer, command):
    """Handle a command read in an interactive session."""
    command_lower = command.lower()
    if command_lower.startswith('back'):
        try:
            moveno = int(command_lower.split(maxsplit=1)[1])
        except (ValueError, IndexError):
            explorer.backtrack()
        else:
            while len(explorer.tree.stack) + 1 != moveno * 2:
                explorer.backtrack()
        explorer.print_stats()
    elif command_lower == 'start':
        explorer.reset()
        explorer.print_stats()
    elif command_lower == 'flip':
        explorer.flip()
        explorer.print_stats()
    elif command_lower == 'board':
        print(explorer.board)
    elif command_lower == 'stats':
        explorer.print_stats()
    elif command_lower == 'games':
        if len(explorer.games) >= 10:
            if not input_yes_no('Display {} results? '.format(len(explorer.games))):
                return
        for game in explorer.games:
            white = game['players']['white']['userId'] or 'Stockfish'
            black = game['players']['black']['userId'] or 'Stockfish'
            print('{} vs. {} ({})'.format(white, black, game['url']))
    elif command_lower == 'help':
        print(textwrap.dedent('''\
                Available commands
                  quit, exit     Exit the program.
                  back <n>       Go back move n, or back one move if n is not given.
                  start          Return to the starting position.
                  flip           Return to the starting position with the opposite color.
                  board          Print the board's current position.
                  stats          Print the stats for each move in the current position.
                  games          Print information about the current games.
                  help           Print this help message.
                  <move>         Make a move on the board. Use standard algebraic notation.
              '''))
    else:
        try:
            explorer.advance(command)
        except ValueError:
            print('No games found.\n')
        else:
            explorer.print_stats()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('username', nargs='?')
    speed_choices = ['bullet', 'blitz', 'rapid', 'classical', 'unlimited', 'correspondence']
    parser.add_argument('--speeds', choices=speed_choices, default=[], nargs='+', metavar='S',
                        help='Limit games to certain time controls: ' + ', '.join(speed_choices))
    parser.add_argument('--months', required=False, type=int, metavar='X',
                        help='Limit games to those played in the past X months')
    parser.add_argument('--exclude-computer', action='store_true',
                        help='Exclude games against the computer')
    parser.add_argument('--refresh-cache', action='store_true',
                        help='Refresh the API cache for the current user')
    parser.add_argument('--no-cache', action='store_true',
                        help='Do not read from or write to the cahce.')
    parser.add_argument('--cachedir', help='Specify the directory for the cache.',
                        default=DEFAULT_CACHE_DIR)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    # I could have argparse do this for me with mutually exclusive groups, but I don't like its
    # error messages.
    if args.no_cache and args.refresh_cache:
        sys.stderr.write('Error: "--no-cache" and "--refresh-cache" are incompatible.\n')
        sys.exit(1)

    if args.no_cache and args.cachedir != DEFAULT_CACHE_DIR:
        sys.stderr.write('Error: "--no-cache" and "--cache" are incompatible.\n')
        sys.exit(1)

    if args.no_cache:
        args.cachedir = ''

    config = Config(username=args.username, speeds=args.speeds, months=args.months,
                    exclude_computer=args.exclude_computer, refresh_cache=args.refresh_cache,
                    verbose=args.verbose, cachedir=args.cachedir)
    run_session(config)
