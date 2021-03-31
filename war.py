"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
#import socketserver
import threading
import sys

# Added struct to handle byte information
import struct


# Namedtuples work like classes, but are much more lightweight so they end
# up being faster. It would be a good idea to keep objects in each of these
# for each game which contain the game's state, for instance things like the
# socket, the cards given, the cards still available, etc.

Game = namedtuple("Game", ["p1", "p2"])

class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    recieved_data = sock.recv(numbytes)
    while len(recieved_data) < numbytes:
        recieved_data += sock.recv(numbytes)
    return recieved_data

def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    game[0].close()
    game[1].close()

    return

def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """

    # Given player one and player two cards,
    # we use the mod operator to compensate
    # for the large integer numbers
    card1 = card1 % 13
    card2 = card2 % 13

    if card1 < card2:
        return -1
    if card1 == card2:
        return 0
    if card1 > card2:
        return 1

    return None

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    # Creating deck of cards
    card_deck = list(range(52))

    # Shuffling them
    random.shuffle(card_deck)

    # Splitting the cards in half and sending them to each player
    player_one_deck = card_deck[:26]
    player_two_deck = card_deck[26:]

    #Note: I used https://docs.python.org/2/library/struct.html
    #to pack the bytes into an object to send it to the clients

    #Player 1 gets the first half of the deck, we're also packing a
    #gamestart value to signify that a game will start between two clients
    player_one_hand = struct.pack('27B', Command.GAMESTART.value, *player_one_deck)
    # Player 2 gets the second half of the deck
    player_two_hand = struct.pack('27B', Command.GAMESTART.value, *player_two_deck)

    return player_one_hand, player_two_hand

def handle_game_clients(player_one, player_two):
    """
    This function will handle two clients at a time in a single game.
    There will be multiple threads that run this function separate from
    each other which allows for multiple games playing at the same time
    """

    # The byte buffer holds 2 bytes which represents the want game value
    byte_buffer = 2

    # Get the byte response from clients
    player_one_data = player_one.recv(byte_buffer)
    player_two_data = player_two.recv(byte_buffer)

    # If a either client sends something that is not a
    # "wantgame" value then we force disconnect both
    if player_one_data != b'\0\0' or player_two_data != b'\0\0':
        kill_game((player_one, player_two))
        return

    # Call the deal_cards function that returns a tuple
    # that will hand out cards to player one and player two
    player_one_hand, player_two_hand = deal_cards()

    # We attempt to send the cards to each player and if anything goes wrong, we kill the game
    try:
        player_one.sendall(player_one_hand)
        player_two.sendall(player_two_hand)
    except socket.error:
        logging.error("Sending cards to players resulted in an error")
        kill_game((player_one, player_two))

    logging.debug("Successfully sent cards to both players")

    # A game will last at most 26 rounds.
    # If anything goes wrong during a game,
    # the game will be killed and clients will force disconnect
    for i in range(1, 27):

        # Receive each player's play card and playcard value
        try:
            player_one_play_card = player_one.recv(byte_buffer)
            player_two_play_card = player_two.recv(byte_buffer)
        except socket.error:
            logging.error("Error happened when receiving response from players during round!")
            kill_game((player_one, player_two))


        # Note: I used https://docs.python.org/2/library/struct.html to unpack the recieved bytes
        # Unpack both messages to get the card values.
        try:
            player_one_data = struct.unpack('2B', player_one_play_card)
            player_two_data = struct.unpack('2B', player_two_play_card)
        except struct.error:
            logging.exception("Struct Exception Occured during game")
            kill_game((player_one, player_two))

        # Get the card value from the player
        player_one_card = player_one_data[1]
        player_two_card = player_two_data[1]

        # If either player sends a value that is not a playcard value then we kill the game
        # Reason: User must send the playcard value because it
        # indicates that the bytestream includes the card they played
        if player_one_data[0] != Command.PLAYCARD.value:
            kill_game((player_one, player_two))
            return

        if player_two_data[0] != Command.PLAYCARD.value:
            kill_game((player_one, player_two))
            return

        # Call compare_cards() to compare card values.
        compared_cards_result = compare_cards(player_one_card, player_two_card)

        # Note: I used https://docs.python.org/2/library/struct.html
        # as help to pack the results of a round
        # and send it back to the player

        # Depending on what the compared_cards_result holds,
        # we will check who win the round and then pack the results for each player by
        # putting into a struct and then send it to the players

        # Player 1 loses and Player 2 wins
        if compared_cards_result == -1:
            player_one_result = struct.pack('2B', Command.PLAYRESULT.value, Result.LOSE.value)
            player_two_result = struct.pack('2B', Command.PLAYRESULT.value, Result.WIN.value)
        # Player 2 loses and Player 1 wins
        elif compared_cards_result == 1:
            player_one_result = struct.pack('2B', Command.PLAYRESULT.value, Result.WIN.value)
            player_two_result = struct.pack('2B', Command.PLAYRESULT.value, Result.LOSE.value)
        # Player 1 and Player 2 Draw
        else:
            player_one_result = struct.pack('2B', Command.PLAYRESULT.value, Result.DRAW.value)
            player_two_result = struct.pack('2B', Command.PLAYRESULT.value, Result.DRAW.value)


        # Attempt to send the results to each of player's socket
        try:
            player_one.sendall(player_one_result)
            player_two.sendall(player_two_result)
        # If anything goes wrong, we kill the game for both players
        except socket.error:
            logging.error("Could not send round results to players!")
            kill_game((player_one, player_two))


        logging.debug("End of Round: %d", i)
    return

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    # Creating TCP sockets for the clients that are connecting
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error:
        logging.error("Socket creation failed.")
        sys.exit()

    logging.debug("Game Server initializing")

    # Bind the client socket
    client_socket.bind((host, port))
    logging.debug("Successfully binded socket")

    # Listen to the client socket for incoming connections
    client_socket.listen()
    logging.debug("Listening to socket for connections...")

    # Infinite loop that will connect 2 incoming clients together and make them play
    while True:
        player_one_socket = client_socket.accept()
        logging.debug("Player 1 connected.")

        player_two_socket = client_socket.accept()
        logging.debug("Player 2 connected.")

        # Creating a new thread for the 2 connected clients using the handle_game_clients
        # as the target function, it will have them play a full game of WAR
        new_game_thread = threading.Thread(target=handle_game_clients,
                                           args=(player_one_socket[0], player_two_socket[0],))
        logging.debug("handle_game_clients function was called in a new thread.")
        new_game_thread.start()
    return

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)


async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port, loop=loop)

        # send want game
        writer.write(b"\0\0")

        card_msg = await reader.readexactly(27)
        myscore = 0

        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1

        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"

        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        loop = asyncio.get_event_loop()

    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
