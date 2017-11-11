#!/usr/bin/env python3
"""An interactive script to play with the lichess API.

Docs for the API can be found at https://github.com/ornicar/lila#http-api
"""
import requests
import time
from collections import Counter


API_ENDPOINT = 'https://lichess.org/api/'


def favorite_opening(username, interactive=True):
    """Return the user's favorite opening from all their games."""
    def handle_api_response(data, openings):
        # Helper function that updates the openings dictionaries with the API response
        for game_obj in data['currentPageResults']:
            try:
                openings[game_obj['opening']['name']] += 1
            except KeyError:
                pass

    url = API_ENDPOINT + 'user/' + username + '/games'
    openings = Counter()
    page = 1
    # Call API for the first time to see how many pages of results there will be.
    payload = {'nb': '100', 'with_opening': '1'}
    r = call_lichess_api(url, interactive=interactive, params=payload)
    data = r.json()
    handle_api_response(data, openings)
    total_pages = data.get('nbPages', 0)
    if interactive is True:
        if total_pages > 15:
            prompt = 'Fetching data will take at least {} seconds. Continue? '.format(total_pages)
            if not input_yes_no(prompt):
                return ''
        else:
            print('Found {} page{}'.format(total_pages, '' if total_pages == 1 else 's'))
    page += 1
    payload['page'] = str(page)
    while page < total_pages:
        if interactive is True:
            print('Fetching page {} of {}'.format(page, total_pages))
        r = call_lichess_api(url, interactive=interactive, params=payload)
        data = r.json()
        handle_api_response(data, openings)
        page += 1
        payload['page'] = str(page)
    return openings.most_common()[0][0]


last_api_call = 0
def call_lichess_api(url, interactive=True, **kwargs):
    """Call the Lichess API, taking care not to send more than one API call per second."""
    global last_api_call
    waiting_time = (last_api_call + 1) - time.time()
    if waiting_time > 0:
        time.sleep(waiting_time)
    r = requests.get(url, **kwargs)
    while r.status_code == 429:
        if interactive is True:
            if input_yes_no('You will have to wait 60 seconds for the next request. Continue? '):
                time.sleep(61)
                r = requests.get(url, **kwargs)
            else:
                return None
        else:
            return None
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
    print('\nYour favorite opening is', favorite_opening(username, interactive=False))
