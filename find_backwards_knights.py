import chess
import chess.pgn
import chess.engine
import io
import os # To check if engine file exists
import time # Import time for EARLY_CHECK_TIME

# --- Configuration ---
# !!! IMPORTANT: Replace with the correct path to your Stockfish executable !!!
STOCKFISH_PATH = r"C:\Users\johns\Downloads\stockfish\stockfish-windows-x86-64-avx2.exe"

# Engine analysis settings (adjust as needed)
# Deeper depth = better analysis but much slower. Time limit is often easier.
ANALYSIS_TIME_LIMIT = 30 # seconds per move evaluation
ANALYSIS_DEPTH_LIMIT = 30 # Alternative: fixed depth
EARLY_CHECK_TIME = 1 # seconds for preliminary check
EARLY_DEPTH_LIMIT = 20

# Threshold for 'significantly better' (in centipawns)
# How much better the backward knight move must be than the next best alternative
SCORE_THRESHOLD = 300 # e.g., 1.5 pawns

# Maximum number of positions to find before stopping
MAX_POSITIONS = 2000

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

        engine.configure({
            "Threads": 11,  # Use 11 physical cores
            "Hash": 12288    # Allocate 12 GB of RAM
        })

        with open(pgn_file_path, 'r', encoding='utf-8', errors='replace') as pgn_file:
            game_count = 0
            while True:
                # Check if we've already found enough positions before processing a new game
                if len(positions) >= MAX_POSITIONS:
                    print(f"Reached maximum position limit ({MAX_POSITIONS}). Stopping game processing.")
                    break

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
                    print(f"  Move {move_number + 1}: {board.san(move)}")

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

                        if len(legal_moves) <= 1:
                             # Only one move, proceed (let push happen below)
                             pass

                        else:
                            # --- Preliminary Analysis (Early Check) ---
                            print(f"  Preliminary check (max {EARLY_CHECK_TIME}s or depth {EARLY_DEPTH_LIMIT}) for position before {move_number}{'...' if current_turn == chess.BLACK else '.'}{board.san(move)}")
                            run_full_analysis = False
                            prelim_failed = False

                            # Get Stockfish's best move and its score (excluding the backward move itself)
                            try:
                                info = engine.analyse(
                                    board,
                                    chess.engine.Limit(time=EARLY_CHECK_TIME, depth=EARLY_DEPTH_LIMIT)
                                )
                                score_obj = info.get("score", None)
                                depth_reached = info.get("depth", None)
                                pv = info.get("pv", [])
                                # Remove backward move from PV if present
                                pv_filtered = [m for m in pv if m.uci() != backward_move_uci]
                                # Only keep moves that are legal in this position
                                legal_uci_set = set(m.uci() for m in legal_moves)
                                pv_filtered = [m for m in pv_filtered if m.uci() in legal_uci_set]
                                if not pv_filtered:
                                    print("    No principal variation from engine (excluding backward move).")
                                    prelim_failed = True
                                else:
                                    best_move = pv_filtered[0]
                                    best_move_uci = best_move.uci()
                                    # Score for best move (from current player's perspective)
                                    temp_board_best = board.copy()
                                    try:
                                        temp_board_best.push(best_move)
                                    except Exception as e:
                                        print(f"    Error: best move {best_move_uci} is not legal in this position: {e}")
                                        prelim_failed = True
                                    if not prelim_failed:
                                        try:
                                            info_best = engine.analyse(
                                                temp_board_best,
                                                chess.engine.Limit(time=EARLY_CHECK_TIME, depth=EARLY_DEPTH_LIMIT)
                                            )
                                            score_obj_best = info_best.get("score", None)
                                            depth_reached_best = info_best.get("depth", None)
                                            if score_obj_best:
                                                if current_turn == chess.WHITE:
                                                    best_score = score_obj_best.white().score(mate_score=30000)
                                                else:
                                                    best_score = score_obj_best.black().score(mate_score=30000)
                                                print(f"    Engine best move (excluding backward): {board.san(best_move)} (score={best_score}, depth={depth_reached_best})")
                                            else:
                                                print(f"    Engine best move (excluding backward): {board.san(best_move)}: no score, depth={depth_reached_best}")
                                                prelim_failed = True
                                        except Exception as e:
                                            print(f"    Error evaluating best move (excluding backward): {e}")
                                            prelim_failed = True

                            except Exception as e:
                                print(f"    Preliminary engine error: {e}")
                                prelim_failed = True

                            # Get score for backward knight move
                            backward_score = None
                            if not prelim_failed:
                                temp_board = board.copy()
                                temp_board.push(chess.Move.from_uci(backward_move_uci))
                                try:
                                    info = engine.analyse(
                                        temp_board,
                                        chess.engine.Limit(time=EARLY_CHECK_TIME, depth=EARLY_DEPTH_LIMIT)
                                    )
                                    score_obj = info.get("score", None)
                                    depth_reached = info.get("depth", None)
                                    if score_obj:
                                        if current_turn == chess.WHITE:
                                            backward_score = score_obj.white().score(mate_score=30000)
                                        else:
                                            backward_score = score_obj.black().score(mate_score=30000)
                                        print(f"    Backward move {board.san(chess.Move.from_uci(backward_move_uci))}: score={backward_score}, depth={depth_reached}")
                                    else:
                                        print(f"    Backward move {board.san(chess.Move.from_uci(backward_move_uci))}: no score, depth={depth_reached}")
                                        prelim_failed = True
                                except Exception as e:
                                    print(f"    Preliminary engine error for backward move: {e}")
                                    prelim_failed = True

                            # Compare scores
                            if prelim_failed or backward_score is None or best_score is None:
                                print(f"    Skipping full analysis: Prelim analysis failed for backward move {backward_move_uci}")
                            else:
                                # If backward move is best or meets threshold, proceed
                                if backward_move_uci == best_move_uci:
                                    print(f"    Preliminary check: Backward move is engine's top choice.")
                                    run_full_analysis = True
                                elif backward_score >= best_score + SCORE_THRESHOLD:
                                    print(f"    Preliminary check: Backward move exceeds best move by threshold ({backward_score} >= {best_score} + {SCORE_THRESHOLD}).")
                                    run_full_analysis = True
                                else:
                                    print(f"    Skipping full analysis: Backward move not best and does not exceed threshold (Backward: {backward_score}, Best: {best_score}, Threshold: {SCORE_THRESHOLD})")
                                    run_full_analysis = False

                            # --- Full Analysis (Only if preliminary check passed) ---
                            if run_full_analysis:
                                print(f"  Running full analysis (Depth={ANALYSIS_DEPTH_LIMIT}, Time={ANALYSIS_TIME_LIMIT}s) for position before {move_number} {'...' if current_turn == chess.BLACK else '.'}{board.san(move)}")
                                scores = {}
                                backward_move_score = None
                                full_failed = False
                                for legal_move in legal_moves:
                                    temp_board = board.copy()
                                    temp_board.push(legal_move)
                                    try:
                                        info = engine.analyse(temp_board, chess.engine.Limit(depth=ANALYSIS_DEPTH_LIMIT, time=ANALYSIS_TIME_LIMIT))
                                        score_obj = info.get("score", None)
                                        depth_reached = info.get("depth", None)
                                        if score_obj:
                                            # Always get score from the perspective of the player who was to move before the move
                                            if current_turn == chess.WHITE:
                                                score = score_obj.white().score(mate_score=30000)
                                            else:
                                                score = score_obj.black().score(mate_score=30000)
                                            scores[legal_move.uci()] = score
                                            if legal_move.uci() == backward_move_uci:
                                                backward_move_score = score
                                            print(f"    Full move {board.san(legal_move)}: score={score}, depth={depth_reached}")
                                        else:
                                            scores[legal_move.uci()] = None
                                            if legal_move.uci() == backward_move_uci:
                                                full_failed = True
                                            print(f"    Full move {board.san(legal_move)}: no score, depth={depth_reached}")
                                    except chess.engine.EngineError as e:
                                        print(f"    Engine analysis error for move {legal_move.uci()}: {e}")
                                        scores[legal_move.uci()] = None
                                        if legal_move.uci() == backward_move_uci:
                                            full_failed = True

                                    # Dynamic check: if this is not the backward move and its score is not None,
                                    # and backward_move_score is already set, check threshold
                                    if (legal_move.uci() != backward_move_uci and
                                        backward_move_score is not None and
                                        scores[legal_move.uci()] is not None):
                                        if backward_move_score < scores[legal_move.uci()] + SCORE_THRESHOLD:
                                            print(f"    Skipping: Full analysis failed threshold (Score: {backward_move_score}, Competing: {scores[legal_move.uci()]}, Threshold: {SCORE_THRESHOLD})")
                                            full_failed = True
                                            break

                                # Check if analysis succeeded for the backward move (using final scores)
                                if full_failed or backward_move_score is None:
                                    print(f"    Skipping: Full analysis failed for backward move {backward_move_uci}")
                                    # Do not continue, let move be pushed below

                                else:
                                    # If we got here, no other move was within threshold
                                    move_san = board.san(move) # Get SAN before push
                                    # Find next best score for reporting
                                    next_best_score = None
                                    for uci, score in scores.items():
                                        if uci != backward_move_uci and score is not None:
                                            if next_best_score is None or score > next_best_score:
                                                next_best_score = score
                                    next_best_score_str = str(next_best_score) if next_best_score is not None else "N/A"

                                    position_info = {
                                        "headers": game.headers,
                                        "fen_before_move": fen_before_move,
                                        "move_number": move_number,
                                        "turn": "White" if current_turn == chess.WHITE else "Black",
                                        "solution_san": move_san,
                                        "solution_score": backward_move_score,
                                        "next_best_score": next_best_score_str,
                                        "all_scores" : {board.san(board.parse_uci(uci)): score for uci, score in scores.items() if score is not None}
                                    }
                                    positions.append(position_info)
                                    print(f"    >>> Found critical backward move: {move_san} (Score: {backward_move_score}, Next Best: {next_best_score_str}) ({len(positions)}/{MAX_POSITIONS})")

                                    # Check if the limit has been reached
                                    if len(positions) >= MAX_POSITIONS:
                                        print(f"Reached maximum position limit ({MAX_POSITIONS}). Stopping analysis for this game.")
                                        break # Exit the move loop for the current game

                    # Always push the move and advance the node, regardless of is_backward or analysis outcome
                    board.push(move)
                    node = next_node

                    # Check if limit was reached within the move loop to break game loop
                    if len(positions) >= MAX_POSITIONS:
                        break # Exit the game loop (while True)

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
    pgn_path = 'twic1591.pgn' # <<< CHANGE THIS

    print(f"Starting analysis on {pgn_path} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Using engine: {STOCKFISH_PATH}")
    print(f"Preliminary check time per move: {EARLY_CHECK_TIME}s") # Added print statement
    print(f"Full analysis limits per move: Depth={ANALYSIS_DEPTH_LIMIT}, Time={ANALYSIS_TIME_LIMIT}s")
    print(f"Score threshold: {SCORE_THRESHOLD}cp")

    found_positions = find_critical_backward_knight_moves(pgn_path, STOCKFISH_PATH)

    if found_positions:
        print(f"\n--- Analysis Complete ---")
        if len(found_positions) >= MAX_POSITIONS:
             print(f"Found {len(found_positions)} positions (stopped after reaching the limit of {MAX_POSITIONS}).")
        else:
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
