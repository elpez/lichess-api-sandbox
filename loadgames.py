import time
import json
import requests
import os
import math
from operator import itemgetter

from typing import List


API_ENDPOINT = 'https://lichess.org/api/'


def fetch_all_games(username: str, *, config=None, **filter_kwargs) -> List[dict]:
    """Return a list of games as lightly-processed JSON objects.

    The JSON objects differ only slightly from those returned by the Lichess API. The `moves`
    member is a list of strings instead of a string. Two fields have been added: `user_color`, which
    is True if the user played White in the game and False otherwise, and `user_result`, which
    is one of ('win', 'draw', 'loss'), relative to the user.

    Games that did not end in a win, loss, or draw (e.g., aborted games) are not returned. Only
    standard chess games are returned - no variants like Chess960.
    """
    # Call API for the first time to see how many pages of results there will be.
    print_verbose('Requesting profile information...', end=' ', flush=True, config=config)
    url = API_ENDPOINT + 'user/' + username + '/games'
    print_verbose('received', flush=True, config=config)
    data = call_lichess_api(url, config=config, params={'nb': 0})
    total_results = data.get('nbResults', 0)
    total_pages = math.ceil(total_results / 100)
    page = 1
    payload = {'nb': 100, 'page': page, 'with_opening': 1, 'with_moves': 1}
    ret = []  # type: List[dict]
    while page <= total_pages:
        print_verbose('Requesting page {} of {}'.format(page, total_pages), config=config)
        data = call_lichess_api(url, config=config, params=payload)
        for game_json in data['currentPageResults']:
            if game_json['variant'] != 'standard' or not game_json['moves']:
                continue
            if game_json['status'] not in ('mate', 'resign', 'stalemate', 'draw'):
                continue
            ret.append(process_game_json(username, game_json))
        page += 1
        payload['page'] = page
    return filter_games(ret, config=config)


def filter_games(games: List[dict], *, config) -> List[dict]:
    if config.speeds:
        games = [g for g in games if g['speed'] in config.speeds]
    if config.months is not None:
        # Times 1000 because Lichess times are in microseconds.
        earliest = (time.time() - 60*60*24*30*config.months) * 1000
        games = [g for g in games if g['createdAt'] >= earliest]
    if config.exclude_computer is True:
        # Computer opponent is indicated by a null userID.
        games = [g for g in games if g['players']['white']['userId'] and
                                     g['players']['black']['userId']]
    return games


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
def call_lichess_api(url, *, config=None, **kwargs) -> dict:
    """Call the Lichess API, taking care not to send more than one API call per second."""
    global last_api_call
    # Try reading the data from the cache first.
    data = read_from_cache(url, config, **kwargs)
    # If we got nothing back from the cache, then hit the URL.
    if data is None:
        waiting_time = (last_api_call + 1.5) - time.time()
        if waiting_time > 0:
            time.sleep(waiting_time)
        print_verbose('Sending request to {}... '.format(url), end='', flush=True, config=config)
        r = requests.get(url, **kwargs)
        while r.status_code == 429:
            print_verbose('received HTTP 429 - waiting a bit to send the next request', flush=True,
                          config=config)
            time.sleep(61)
            print_verbose('Sending request to {}... '.format(url), end='', flush=True,
                                                                   config=config)
            r = requests.get(url, **kwargs)
        print_verbose('received!', flush=True, config=config)
        last_api_call = time.time()
        data = r.json()
        write_to_cache(url, data, config, **kwargs)
    return data


def read_from_cache(url: str, config, **kwargs) -> List[dict]:
    """Look up the URL in the cache and return its cached result, or None on failure."""
    if config.refresh_cache or not config.cachedir:
        return None
    fpath = os.path.join(config.cachedir, url_to_fpath(url, **kwargs))
    try:
        print_verbose('Trying to open cache file {}... '.format(fpath), end='', flush=True,
                                                                        config=config)
        with open(fpath, 'r') as fsock:
            data = json.load(fsock)
    except (FileNotFoundError, IOError, json.decoder.JSONDecodeError):
        print_verbose('failed!', flush=True, config=config)
        return None
    else:
        print_verbose('succeeded!', flush=True, config=config)
        return data


def write_to_cache(url: str, data: List[dict], config, **kwargs) -> None:
    """Write to the cache, if `config` allows it."""
    if not config.cachedir:
        return
    print_verbose('Writing to cache file ' + url, config=config)
    fpath = os.path.join(config.cachedir, url_to_fpath(url, **kwargs))
    with open(os.path.join(config.cachedir, url_to_fpath(url, **kwargs)), 'w') as fsock:
        json.dump(data, fsock)


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


def print_verbose(*args, config, **kwargs):
    """A shortcut for `if config and config.verbose: print(*args, **kwargs)`"""
    if config and config.verbose:
        print(*args, **kwargs)
