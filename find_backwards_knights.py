import chess
import chess.pgn
import chess.engine
import io
import os # To check if engine file exists

# --- Configuration ---
# !!! IMPORTANT: Replace with the correct path to your Stockfish executable !!!
STOCKFISH_PATH = "/usr/local/bin/stockfish" # Example for Linux/macOS
# STOCKFISH_PATH = "C:/path/to/stockfish/stockfish.exe" # Example for Windows

# Engine analysis settings (adjust as needed)
# Deeper depth = better analysis but much slower. Time limit is often easier.
ANALYSIS_TIME_LIMIT = 0.5 # seconds per move evaluation
# ANALYSIS_DEPTH_LIMIT = 15 # Alternative: fixed depth

# Threshold for 'significantly better' (in centipawns)
# How much better the backward knight move must be than the next best alternative
SCORE_THRESHOLD = 150 # e.g., 1.5 pawns

def find_critical_backward_knight_moves(pgn_file_path, engine_path):
    """
    Parses a PGN, finds backward knight moves, and uses an engine
    to check if they were significantly better than alternatives.

    Args:
        pgn_file_path (str): Path to the PGN file.
        engine_path (str): Path to the UCI engine executable.

    Returns:
        list: Dictionaries containing info about qualifying positions
              (FEN before move, solution move SAN, game headers, scores).
    """
    if not os.path.exists(engine_path):
        print(f"Error: Stockfish engine not found at {engine_path}")
        print("Please download Stockfish and update STOCKFISH_PATH in the script.")
        return []

    positions = []
    engine = None # Initialize engine variable

    try:
        # Start the engine process
        engine = chess.engine.SimpleEngine.popen_uci(engine_path)

        with open(pgn_file_path, 'r', encoding='utf-8', errors='replace') as pgn_file:
            game_count = 0
            while True:
                game = chess.pgn.read_game(pgn_file)
                if game is None:
                    break
                game_count += 1
                print(f"Processing game {game_count}...") # Progress indicator

                board = game.board()
                move_number = 0
                is_white_turn_for_fullmove_counter = True

                node = game # Start from the beginning node
                while node.variations:
                    next_node = node.variations[0]
                    move = next_node.move

                    # Update move number logic
                    current_turn = board.turn
                    if current_turn == chess.WHITE:
                        move_number += 1

                    # Check for backward knight move
                    is_backward = False
                    piece = board.piece_at(move.from_square)
                    if piece and piece.piece_type == chess.KNIGHT:
                        from_rank = chess.square_rank(move.from_square)
                        to_rank = chess.square_rank(move.to_square)

                        if current_turn == chess.WHITE and to_rank < from_rank:
                            is_backward = True
                        elif current_turn == chess.BLACK and to_rank > from_rank:
                            is_backward = True

                    if is_backward:
                        # --- Engine Analysis Required ---
                        fen_before_move = board.fen()
                        backward_move_uci = move.uci()
                        legal_moves = list(board.legal_moves)
                        scores = {} # move.uci() -> score (relative cp)

                        if len(legal_moves) <= 1:
                             board.push(move) # Only one move, proceed
                             node = next_node
                             continue # Skip analysis if only one move possible

                        print(f"  Analyzing position before move {move_number} {'...' if current_turn == chess.BLACK else '.'}{board.san(move)}")

                        # Analyze each legal move
                        for legal_move in legal_moves:
                            temp_board = board.copy()
                            temp_board.push(legal_move)
                            try:
                                # Use time limit for analysis
                                info = engine.analyse(temp_board, chess.engine.Limit(time=ANALYSIS_TIME_LIMIT))
                                # Use depth limit (alternative)
                                # info = engine.analyse(temp_board, chess.engine.Limit(depth=ANALYSIS_DEPTH_LIMIT))

                                # Get relative score (good for current player)
                                # Handle potential None scores if analysis fails quickly
                                score_obj = info.get("score", None)
                                if score_obj:
                                    relative_score = score_obj.relative
                                    # Use mate_score to handle checkmates appropriately
                                    scores[legal_move.uci()] = relative_score.score(mate_score=30000)
                                else:
                                     scores[legal_move.uci()] = None # Mark as failed analysis
                            except chess.engine.EngineError as e:
                                print(f"    Engine analysis error for move {legal_move.uci()}: {e}")
                                scores[legal_move.uci()] = None # Mark as failed

                        # Check if analysis succeeded for the backward move
                        if backward_move_uci not in scores or scores[backward_move_uci] is None:
                            print(f"    Skipping: Analysis failed for backward move {backward_move_uci}")
                            board.push(move) # Make the move and continue
                            node = next_node
                            continue

                        backward_move_score = scores[backward_move_uci]
                        other_scores = [s for uci, s in scores.items() if uci != backward_move_uci and s is not None]

                        is_only_good_move = False
                        next_best_score_str = "N/A"
                        if not other_scores:
                            # The backward move was the only one analyzed successfully (or only one move)
                            is_only_good_move = True
                        else:
                            next_best_score = max(other_scores)
                            next_best_score_str = str(next_best_score)
                            # Check if the backward move's score is significantly better
                            if backward_move_score >= next_best_score + SCORE_THRESHOLD:
                                is_only_good_move = True

                        # Store if it meets the criteria
                        if is_only_good_move:
                            move_san = board.san(move) # Get SAN before push
                            position_info = {
                                "headers": game.headers,
                                "fen_before_move": fen_before_move,
                                "move_number": move_number,
                                "turn": "White" if current_turn == chess.WHITE else "Black",
                                "solution_san": move_san,
                                "solution_score": backward_move_score,
                                "next_best_score": next_best_score_str,
                                "all_scores" : {board.san(board.parse_uci(uci)): score for uci, score in scores.items() if score is not None} # Store for context
                            }
                            positions.append(position_info)
                            print(f"    >>> Found critical backward move: {move_san} (Score: {backward_move_score}, Next Best: {next_best_score_str})")

                    # --- End of Analysis ---
                    # Apply the move to the board to continue iterating through the game
                    board.push(move)
                    node = next_node # Move to the next node in PGN

    except FileNotFoundError:
        print(f"Error: PGN file not found at {pgn_file_path}")
    except chess.engine.EngineTerminatedError:
         print(f"Error: Engine terminated unexpectedly. Check engine path and permissions.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # Ensure the engine is closed properly
        if engine:
            engine.quit()

    return positions

# --- How to use it ---
if __name__ == "__main__":
    # Record start time for performance check
    import time
    start_time = time.time()

    # Replace with the actual path to your PGN file
    pgn_path = 'your_games.pgn' # <<< CHANGE THIS

    print(f"Starting analysis on {pgn_path} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Using engine: {STOCKFISH_PATH}")
    print(f"Analysis time limit per move: {ANALYSIS_TIME_LIMIT}s")
    print(f"Score threshold: {SCORE_THRESHOLD}cp")

    found_positions = find_critical_backward_knight_moves(pgn_path, STOCKFISH_PATH)

    if found_positions:
        print(f"\n--- Analysis Complete ---")
        print(f"Found {len(found_positions)} positions where a backward knight move was significantly better.")

        # Example: Print details of the first 5 found positions
        for i, pos in enumerate(found_positions[:5]):
            print(f"\nPosition {i+1}:")
            print(f"  Game: {pos['headers'].get('White', '?')} vs {pos['headers'].get('Black', '?')} ({pos['headers'].get('Event', '?')})")
            print(f"  FEN (before move): {pos['fen_before_move']}")
            print(f"  Turn: {pos['turn']}")
            print(f"  Critical Move (Solution): {pos['move_number']}{'.' if pos['turn'] == 'White' else '...'} {pos['solution_san']}")
            print(f"  Solution Score: {pos['solution_score']}cp")
            print(f"  Next Best Score: {pos['next_best_score']}cp")
            # print(f"  All Move Scores: {pos['all_scores']}") # Uncomment for more detail

        # Next step: Save these positions (e.g., FENs and solution moves) to a new file
        # for your course creation.
    else:
        print("\n--- Analysis Complete ---")
        print("No positions meeting the criteria were found.")

    end_time = time.time()
    print(f"\nTotal analysis time: {end_time - start_time:.2f} seconds.")
    # Adding current time as requested in context
    print(f"Script finished at: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
