import time
import json
import requests
import os
import math
from operator import itemgetter

from typing import List


API_ENDPOINT = 'https://lichess.org/api/'
CACHE_DIR = '.lichess_cache'


def fetch_all_games(username: str, *, verbose=False, refresh_cache=False) -> List[dict]:
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
    data = call_lichess_api(url, refresh_cache=refresh_cache, verbose=verbose, params={'nb': 0})
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


last_api_call = 0.0
def call_lichess_api(url, refresh_cache=False, verbose=False, **kwargs) -> dict:
    """Call the Lichess API, taking care not to send more than one API call per second."""
    global last_api_call
    fpath = os.path.join(CACHE_DIR, url_to_fpath(url, **kwargs))
    if not refresh_cache and os.path.exists(fpath):
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
