import sys, socket, threading, json
from queue import Queue

# Posioned Chocolate Game Logic
class PoisonedChocolate:
    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.board = [[True for _ in range(cols)] for _ in range(rows)] # True = uneaten
        self.turn = 1  # Player 1 starts if player 0 picks board size
        self.winner = None

    # ensures move within board
    def valid_move(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols and self.board[r][c]

    def make_move(self, r, c):
        if not self.valid_move(r, c) or self.winner is not None:
            return False
        
        # eats board to top right corner
        for i in range(r, self.rows):
            for j in range(c, self.cols):
                self.board[i][j] = False
        
        # Sets winner if "posioned chocolate" is eaten
        if not self.board[0][0]:
            self.winner = 0 if self.turn == 1 else 1
        # or Switches turn if not eaten
        else:
            self.turn = 0 if self.turn == 1 else 1
        return True

    # prints board with row and column numbers to make gameplay easier
    def render(self):
        # ensures row/column numbers line up with the "squares"
        max_row_digits = len(str(self.rows - 1))
        max_col_digits = len(str(self.cols - 1))
        cell_width = max(1, max_col_digits)  # space per column

        # column headers
        col_headers = " " * (max_row_digits + 1)  # left padding for row numbers
        col_headers += " ".join(f"{c:{cell_width}}" for c in range(self.cols))
        lines = [col_headers]

        # board rows with row numbers
        for r, row in enumerate(reversed(self.board)):
            row_num = self.rows - 1 - r
            line = f"{row_num:{max_row_digits}} "  # row number
            line += " ".join(f"{'X' if cell else '.':{cell_width}}" for cell in row)
            lines.append(line)

        return "\n".join(lines)

# sends JSON to server
def send_json(sock, arr):
    try:
        sock.sendall((json.dumps(arr) + "\n").encode("utf-8"))
    except Exception:
        pass

# Listens for and handles incoming JSON to play Poisoned Chocolate
# sock: socket object
# game_queue: Thread to process game
# game_started_flag: Boolean to track if game started
# player_id: 0 or 1
# game_ref: Posioned Chocolate game object
def listen(sock, game_queue, game_started_flag, player_id, game_ref):
    f = sock.makefile("r", encoding="utf-8", newline="\n")
    while True:
        line = f.readline()
        if not line:
            print("Disconnected from server")
            break
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except Exception:
            continue

        print("<<", msg)

        # Matched with a player
        if msg[0] == 110:
            room_id, role = msg[1], msg[2]
            print(f"Matched! Room: {room_id}, Role: {role}")
            player_id[0] = role
            if role == 0:
                # Player 0 chooses board
                while True:
                    try:
                        raw = input("Enter board size (rows cols): ")
                        rows, cols = map(int, raw.split())
                        # enforces board to be atleast 2x2
                        if rows > 1 and cols > 1:
                            break
                        else:
                            print("Board must be at least 2x2.")
                    except Exception:
                        print("Invalid input, try again.")
                
                # sends board size to other player
                send_json(sock, [210, "size", rows, cols])
                print(f">> Sent board size {rows}x{cols}")

                # Initialize board for player 0
                game_ref[0] = PoisonedChocolate(rows, cols)
                game_started_flag[0] = True
                print(f"Game started: {rows}x{cols}")
                print(game_ref[0].render())
                # Player 0 goes second
                game_queue.put(("wait_turn", None))

        # For player 1, creates board when player 0 sends board size
        elif msg[0] == 210:
            _, _, rows, cols = msg
            game_ref[0] = PoisonedChocolate(rows, cols)
            game_started_flag[0] = True
            print(f"Game started: {rows}x{cols}")
            print(game_ref[0].render())
            # Player 1 starts
            if player_id[0] == 1:
                game_queue.put(("your_turn", None))

        # Opponent moved
        elif msg[0] == 220:
            _, _, r, c = msg
            game_queue.put(("opponent_move", r, c))

        # Opponent left
        elif msg[0] == 111:
            if game_started_flag[0]:
                print("Opponent disconnected.")
                game_queue.put(("end", None))
            else:
                print("Opponent Left.")

# Game loop
def game_loop(sock, player_id):
    game_queue = Queue()
    game_started_flag = [False]
    game = [None]
    my_turn = False

    # Thread for listening to incoming JSON
    threading.Thread(target=listen, args=(sock, game_queue, game_started_flag, player_id, game), daemon=True).start()

    # Queues matchmaking
    send_json(sock, [100])
    print(">> [100] (Queued for matchmaking)")

    while True:
        # Process messages from listener
        # Determines whose turn and what moves were made
        while not game_queue.empty():
            item = game_queue.get()
            if item[0] == "your_turn":
                my_turn = True
            elif item[0] == "wait_turn":
                my_turn = False
            elif item[0] == "opponent_move":
                r, c = item[1], item[2]
                if game[0]:
                    game[0].make_move(r, c)
                    print(f"Opponent moved at ({r},{c})")
                    print(game[0].render())
                    if game[0].winner is None:
                        my_turn = True
            elif item[0] == "end":
                return

        # Prompt player for move if it is their turn
        # This also ensures that moves are valid
        if my_turn and game[0] and game[0].winner is None:
            try:
                raw = input("Enter Move (row col): ")
                r, c = map(int, raw.split())
                if game[0].valid_move(r, c):
                    game[0].make_move(r, c)
                    send_json(sock, [220, "move", r, c])
                    print(">> Sent move")
                    print(game[0].render())
                    my_turn = False
                    if game[0].winner is not None:
                        print(f"Game over! Winner: Player {game[0].winner}")
                        return
                else:
                    print("Invalid move, try again.")
            except Exception:
                print("Bad input, try again.")

# Connects to server via host and port
def server_connect(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    print(f"Connected to {(host, port)}")

    player_id = [None]

    try:
        game_loop(s, player_id)
    except KeyboardInterrupt:
        send_json(s, [101])
        print(">> Sent LEAVE via Ctrl+C")
    finally:
        s.close()
        print("Connection closed.")

# main
def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <host> <port>")
        return
    host, port = sys.argv[1], int(sys.argv[2])
    server_connect(host, port)

if __name__ == "__main__":
    main()