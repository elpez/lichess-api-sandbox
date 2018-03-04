# lichess-movetree
Explore all the moves you've ever made in your [Lichess](https://lichess.org) games.


## Installation
Install the packages from `requirements.txt`. Python 3.4+ is required.

```
$ git clone https://github.com/elpez/lichess-movetree.git
$ cd lichess-movetree
$ pip install -r requirements.txt
```


## Usage
Run the `movetree.py` script, optionally passing your Lichess username as a command-line argument
(you will be prompted to enter it otherwise). The script will try to fetch all of your games. This
may take some time, as Lichess only allows 100 games to be downloaded in one batch. After the
initial download, loading should be super fast as the script caches the API results.

Voilà! The script should tell you all the opening moves you've played as White, with the percentages
of wins, draws and losses for each. For example,

```
$ ./movetree.py iafisher

Loading user data...


YOUR MOVES (from 460 games)
1. d4      (you won  52.6%, lost  43.0%, and drew   4.4%, from 249 games)
1. e4      (you won  51.0%, lost  42.3%, and drew   6.7%, from 208 games)
1. c4      (you won 100.0%, lost   0.0%, and drew   0.0%, from 1 game)
1. e3      (you won   0.0%, lost   0.0%, and drew 100.0%, from 1 game)
1. g3      (you won 100.0%, lost   0.0%, and drew   0.0%, from 1 game)

white>>>
```

Enter one of the moves to see all your opponents' responses. Type `back` to undo the last move, or `back 3` to go back to the third move. Type `board` to view the board (courtesy of [python-chess](https://github.com/niklasf/python-chess)). Type `flip` to see all your moves as Black. Type `help` to see all the available commands. `quit` or `exit` will end the script.
