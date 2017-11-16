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
Run the `lichess.py` script, optionally passing your Lichess username as a command-line argument
(you will be prompted to enter it otherwise). The script will try to fetch all of your games. This
may take some time, as Lichess only allows 100 games to be downloaded in one batch. After the
initial download, loading should be super fast as the script caches the API results.

Voilà! The script should tell you all the opening moves you've played as White, with the percentages
of wins, draws and losses for each. For example,

```
$ ./lichess.py iafisher

Loading user data...

YOUR MOVES (from 502 games)
d4      (you won  58.82%, drew   3.68%, and lost  37.50%, from 272 games)
e4      (you won  53.95%, drew   6.14%, and lost  39.91%, from 228 games)
e3      (you won   0.00%, drew 100.00%, and lost   0.00%, from 1 game)
c4      (you won 100.00%, drew   0.00%, and lost   0.00%, from 1 game)

white>>> 
```

Enter one of the moves to see all your opponents' responses. Type `back` to undo the last move. Type
 `board` to view the board (courtesy of [python-chess](https://github.com/niklasf/python-chess)). 
Type `black` to see all your moves as Black. `quit` or `exit` will end the script.
