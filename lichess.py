#!/usr/bin/env python3
"""An interactive script to play with the Lichess API.

Docs for the API can be found at https://github.com/ornicar/lila#http-api
"""
import requests
import time
import math
import json
import os
import argparse
import readline
import textwrap
import shutil
from operator import itemgetter, attrgetter
from collections import Counter, namedtuple

from typing import List, Dict, Optional, Tuple

import chess


API_ENDPOINT = 'https://lichess.org/api/'
CACHE_DIR = '.lichess_cache'


def fetch_all_games(username: str, *, verbose=False) -> List[dict]:
    """Return a list of games as lightly-processed JSON objects.

    The JSON objects differ only slightly from those returned by the Lichess API. The `moves`
    member is a list of strings instead of a string. Two fields have been added: `user_color`, which
    is True if the user played White in the game and False otherwise, and `user_result`, which
    is one of ('win', 'draw', 'loss'), relative to the user.

    Games that did not end in a win, loss, or draw (e.g., aborted games) are not returned. Only
    standard chess games are returned - no variants like Chess960.
    """
    # Call API for the first time to see how many pages of results there will be.
    if verbose is True:
        print('Requesting profile information...', end=' ', flush=True)
    url = API_ENDPOINT + 'user/' + username + '/games'
    if verbose is True:
        print('received', flush=True)
    data = call_lichess_api(url, verbose=verbose, params={'nb': 0})
    total_results = data.get('nbResults', 0)
    total_pages = math.ceil(total_results / 100)
    page = 1
    payload = {'nb': 100, 'page': page, 'with_opening': 1, 'with_moves': 1}
    ret = []  # type: List[dict]
    while page <= total_pages:
        if verbose is True:
            print('Requesting page {} of {}...'.format(page, total_pages), end=' ', flush=True)
        data = call_lichess_api(url, verbose=verbose, params=payload)
        if verbose is True:
            print('received', flush=True)
        for game_json in data['currentPageResults']:
            if game_json['variant'] != 'standard' or not game_json['moves']:
                continue
            if game_json['status'] not in ('mate', 'resign', 'stalemate', 'draw'):
                continue
            ret.append(process_game_json(username, game_json))
        page += 1
        payload['page'] = page
    return ret


def process_game_json(username: str, game_json: dict) -> dict:
    # Split the `moves` string into a list for easier processing.
    game_json['moves'] = game_json['moves'].split(' ')
    # Add `user_color` and `user_result` information.
    if game_json['players']['white']['userId'] == username:
        game_json['user_color'] = True
    else:
        game_json['user_color'] = False
    if game_json['status'] in ('stalemate', 'draw'):
        game_json['user_result'] = 'draw'
    else:
        winner = True if game_json['winner'] == 'white' else False
        if winner == game_json['user_color']:
            game_json['user_result'] = 'win'
        else:
            game_json['user_result'] = 'loss'
    return game_json


def filter_games(games, moves_so_far):
    """Return an iterator over all games that began with the given moves."""
    return (game for game in games if game['moves'][:len(moves_so_far)] == moves_so_far)


last_api_call = 0.0
def call_lichess_api(url, use_cache=True, verbose=False, **kwargs) -> dict:
    """Call the Lichess API, taking care not to send more than one API call per second."""
    global last_api_call
    fpath = os.path.join(CACHE_DIR, url_to_fpath(url, **kwargs))
    if use_cache and os.path.exists(fpath):
        with open(fpath, 'r') as fsock:
            data = json.load(fsock)
        return data
    else:
        waiting_time = (last_api_call + 1.5) - time.time()
        if waiting_time > 0:
            time.sleep(waiting_time)
        r = requests.get(url, **kwargs)
        while r.status_code == 429:
            if verbose is True:
                print('Received HTTP 429 - waiting a bit to send the next request')
            time.sleep(61)
            r = requests.get(url, **kwargs)
        last_api_call = time.time()
        data = r.json()
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)
        with open(os.path.join(CACHE_DIR, url_to_fpath(url, **kwargs)), 'w') as fsock:
            json.dump(data, fsock)
        return data


def url_to_fpath(url: str, **kwargs) -> str:
    """Convert a URL to a file path, for caching."""
    # Strip off the common prefix.
    url = url[len(API_ENDPOINT):]
    url = url.replace('/', '_')
    params_dict = kwargs.get('params')
    if params_dict:
        sorted_dict = sorted(params_dict.items(), key=itemgetter(0))
        params_str = '_'.join(key + '=' + str(val) for key, val in sorted_dict)
        return url + '_' + params_str + '.json'
    else:
        return url + '.json'


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


# I may switch this to use a more robust opening book, like the one in the python-chess package.
OPENING_NAMES = {
    ('e4', 'c5'): 'Sicilian Defense',
    ('e4', 'c5', 'Nf3', 'd6', 'd4', 'cxd4', 'Nxd4', 'Nf6', 'Nc3', 'a6'): 'Sicilian Defense, Najdorf Variation',
    ('e4', 'c5', 'Nf3', 'd6', 'd4', 'cxd4', 'Nxd4', 'Nf6', 'Nc3', 'g6'): 'Sicilian Dragon',
    ('e4', 'c5', 'Nf3', 'd6', 'd4', 'cxd4', 'Nxd4', 'g6'): 'Sicilian Defense, Accelerated Dragon',
    ('e4', 'c5', 'Nf3', 'Nc6'): 'Old Sicilian',
    ('e4', 'c6'): 'Caro-Kann Defense',
    ('e4', 'e6'): 'French Defense',
    ('e4', 'd5'): 'Scandinavian Defense',
    ('e4', 'Nf6'): "Alekhine's Defense",
    ('e4', 'g6'): 'Modern Defense',
    ('e4', 'e5', 'Nc3'): 'Vienna Game',
    ('e4', 'e5', 'd4'): 'Center Game',
    ('e4', 'e5', 'f4'): "King's Gambit",
    ('e4', 'e5', 'Nf3', 'Nf6'): "Petrov's Defense",
    ('e4', 'e5', 'Nf3', 'f5'): 'Latvian Gambit',
    ('e4', 'e5', 'Nf3', 'd6'): 'Philidor Defense',
    ('e4', 'e5', 'Nf3', 'd5'): 'Elephant Gambit',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bb5'): 'Ruy Lopez',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6'): 'Ruy Lopez, Morphy Defense',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'd6'): 'Ruy Lopez, Steinitz Defense',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'Nf6'): 'Ruy Lopez, Berlin Defense',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4'): 'Italian Game',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5'): 'Giuco Piano',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5', 'b4'): 'Italian Game, Evans Gambit',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Nf6', 'Ng5'): 'Fried Liver Attack',
    ('e4', 'e5', 'Nf3', 'Nc6', 'Nc3'): "Three Knight's Game",
    ('e4', 'e5', 'Nf3', 'Nc6', 'Nc3', 'Nf6'): "Four Knight's Game",
    ('e4', 'e5', 'Nf3', 'Nc6', 'd4'): 'Scotch Game',
    ('e4', 'e5', 'Nf3', 'Nc6', 'c3'): 'Ponziani Opening',
    ('d4', 'Nf6'): 'Indian Defense',
    ('d4', 'Nf6', 'c4', 'g6'): "King's Indian Defense",
    ('d4', 'Nf6', 'c4', 'e6', 'Nc3', 'Bb4'): 'Nimzo-Indian Defense',
    ('d4', 'd5', 'c4'): "Queen's Gambit",
    ('d4', 'd5', 'c4', 'e6'): "Queen's Gambit Declined",
    ('d4', 'd5', 'c4', 'c6'): 'Slav Defense',
    ('c4',): 'English Opening',
    ('Nf3',): 'Reti Opening',
    ('a3',): 'Anderssen Opening',
    ('a4',): 'Ware Opening',
    ('b3',): 'Nimzo-Larsen Attack',
    ('b4',): 'Polish Opening',
    ('c3',): 'Saragossa Opening',
    ('d3',): 'Mieses Opening',
    ('e3',): "Van't Krujis Opening",
    ('f3',): "Gedult's Opening",
    ('f4',): 'Bird Opening',
    ('g3',): 'Hungarian Opening',
    ('g4',): 'Grob Opening',
    ('h3',): 'Clemenz Opening',
    ('h4',): 'Kadas Opening',
}


class MoveExplorer:
    """Explore the moves from all the games of a given Lichess user."""

    def __init__(self, username: str, color: bool, **kwargs) -> None:
        self.all_games = fetch_all_games(username, **kwargs)
        self._init_everything_else(color)

    def _init_everything_else(self, color: bool) -> None:
        self.color = color
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
            self.games = [g for g in filter_games(self.all_games, self.tree.stack)
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
        self._init_everything_else(not self.color)

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
            # I believe that Ng3xe5+ (7 chars) is the longest possible chess move in strict
            # algebraic notation.
            print('{:7}'.format(move), end='')
            print(' (you won {:7,.2%}, drew {:7,.2%},'.format(wins, draws), end='')
            print(' and lost {:7,.2%}'.format(losses), end='')
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
    return string.format(n, '' if n == 1 else 's')



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('username', nargs='?')
    parser.add_argument('--clear-cache', action='store_true', help='clear the Lichess API cache')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()
    if args.clear_cache is True:
        for fpath in os.listdir(CACHE_DIR):
            os.remove(os.path.join(CACHE_DIR, fpath))
    if args.username is not None:
        username = args.username
    else:
        username = input('Please enter your Lichess username: ').strip()
    print('\nLoading user data...\n')
    explorer = MoveExplorer(username, True, verbose=args.verbose)
    explorer.print_stats()
    while True:
        while True:
            response = input('{}>>> '.format('white' if explorer.color else 'black')).strip()
            if response:
                break
        response_lower = response.lower()
        if response.lower() in ('quit', 'exit'):
            break
        elif response_lower == 'back':
            explorer.backtrack()
            explorer.print_stats()
        elif response_lower == 'flip':
            explorer.flip()
            explorer.print_stats()
        elif response_lower == 'board':
            print(explorer.board)
        elif response_lower == 'stats':
            explorer.print_stats()
        elif response_lower == 'help':
            print(textwrap.dedent('''\
                    Available commands
                      quit, exit     Exit the program.
                      back           Go back one move.
                      flip           Return to the starting position with the opposite color.
                      board          Print the board's current position.
                      stats          Print the stats for each move in the current position.
                      help           Print this help message.
                      <move>         Make a move on the board. Use standard algebraic notation.
                  '''))
        else:
            try:
                explorer.advance(response)
            except ValueError:
                print('No games found.\n')
            else:
                explorer.print_stats()
