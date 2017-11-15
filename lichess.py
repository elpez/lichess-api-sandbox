#!/usr/bin/env python3
"""An interactive script to play with the lichess API.

Docs for the API can be found at https://github.com/ornicar/lila#http-api
"""
import requests
import time
import math
from collections import Counter


API_ENDPOINT = 'https://lichess.org/api/'


class Profile:
    def __init__(self, username):
        self.username = username
        self.real_name = ''
        self.bullet_rating = 0
        self.bullet_games = 0
        self.blitz_rating = 0
        self.blitz_games = 0
        self.classical_rating = 0
        self.classical_games = 0
        self.openings = Counter()
        self.first_moves_as_white = Counter()
        self.responses_to_e4 = Counter()
        self.responses_to_d4 = Counter()

    def build(self, interactive=True):
        r = call_lichess_api(API_ENDPOINT + 'user/' + self.username, interactive=interactive)
        data = r.json()
        # Get profile information.
        json_profile = data.get('profile')
        if json_profile:
            first_name = json_profile.get('firstName', '')
            last_name = json_profile.get('lastName', '')
            if first_name and last_name:
                self.real_name = first_name + ' ' + last_name
            elif first_name or last_name:
                self.real_name = first_name + last_name
        # Get rating information.
        json_perf = data['perfs']
        json_bullet = json_perf.get('bullet')
        if json_bullet:
            self.bullet_rating = json_bullet['rating']
            self.bullet_games = json_bullet['games']
        json_blitz = json_perf.get('blitz')
        if json_blitz:
            self.blitz_rating = json_blitz['rating']
            self.blitz_games = json_blitz['games']
        json_classical = json_perf.get('classical')
        if json_classical:
            self.classical_rating = json_classical['rating']
            self.classical_games = json_classical['games']
        # Get game information.
        # Call API for the first time to see how many pages of results there will be.
        url = API_ENDPOINT + 'user/' + username + '/games'
        r = call_lichess_api(url, interactive=interactive, params={'nb': 0})
        data = r.json()
        total_results = data.get('nbResults', 0)
        total_pages = math.ceil(total_results / 100)
        if interactive is True:
            if total_pages > 15:
                prompt = 'Fetching data will take at least %s seconds. Continue? ' % total_pages
                if not input_yes_no(prompt):
                    return
        page = 1
        payload = {'nb': 100, 'page': page, 'with_opening': 1, 'with_moves': 1}
        while page <= total_pages:
            r = call_lichess_api(url, interactive=interactive, params=payload)
            print('Fetched page {}'.format(page))
            data = r.json()
            for game_obj in data['currentPageResults']:
                self._process_game(game_obj)
            page += 1
            payload['page'] = page

    def _process_game(self, game_json):
        try:
            self.openings[game_json['opening']['name']] += 1
        except KeyError:
            pass
        moves = game_json['moves']
        first_move = moves[:2]
        if game_json['players']['white']['userId'] == self.username:
            self.first_moves_as_white[first_move] += 1
        else:
            if first_move == 'e4':
                self.responses_to_e4[moves[3:5]] += 1
            elif first_move == 'd4':
                self.responses_to_d4[moves[3:5]] += 1

    def prettyprint(self):
        if self.real_name:
            print('=== {0.username} ({0.real_name}) ===\n'.format(self))
        else:
            print('=== {0.username} ===\n'.format(self))
        if self.bullet_games > 0:
            print('Bullet rating: {0.bullet_rating} over {0.bullet_games} game(s)'.format(self))
        if self.blitz_games > 0:
            print('Blitz rating: {0.blitz_rating} over {0.blitz_games} game(s)'.format(self))
        if self.classical_games > 0:
            print('Classical rating: {0.classical_rating} over {0.classical_games} game(s)'.format(self))
        if self.bullet_games > 0 or self.blitz_games > 0 or self.classical_games > 0:
            print()

        print('Favorite openings')
        for i, (opening, count) in enumerate(self.openings.most_common(3), start=1):
            print('  {}. {} ({} game{})'.format(i, opening, count, '' if count == 1 else 's'))
        print()

        print('Favorite responses to 1. e4')
        for i, (move, count) in enumerate(self.responses_to_e4.most_common(3), start=1):
            print('  {}. {} ({} game{})'.format(i, move, count, '' if count == 1 else 's'))
        print()

        print('Favorite responses to 1. d4')
        for i, (move, count) in enumerate(self.responses_to_d4.most_common(3), start=1):
            print('  {}. {} ({} game{})'.format(i, move, count, '' if count == 1 else 's'))
        print()


last_api_call = 0
def call_lichess_api(url, interactive=False, **kwargs):
    """Call the Lichess API, taking care not to send more than one API call per second."""
    global last_api_call
    waiting_time = (last_api_call + 1.5) - time.time()
    if waiting_time > 0:
        time.sleep(waiting_time)
    r = requests.get(url, **kwargs)
    while r.status_code == 429:
        if interactive is True:
            print('Sleeping')
        time.sleep(61)
        r = requests.get(url, **kwargs)
    last_api_call = time.time()
    return r


def input_yes_no(*args, **kwargs):
    while True:
        response = input(*args, **kwargs).strip().lower()
        if response.startswith('y'):
            return True
        elif response.startswith('n'):
            return False


if __name__ == '__main__':
    username = input('Please enter your lichess username: ').strip()
    p = Profile(username)
    p.build()
    print()
    p.prettyprint()
