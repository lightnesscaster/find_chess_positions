import chess
import chess.pgn
import chess.engine
import io
import os # To check if engine file exists
import time # Import time for EARLY_CHECK_TIME

# --- Configuration ---
# !!! IMPORTANT: Replace with the correct path to your Stockfish executable !!!
STOCKFISH_PATH = "/Users/danieljohnston/Downloads/stockfish/stockfish-macos-m1-apple-silicon" # <<< CHANGE THIS

# Engine analysis settings (adjust as needed)
# Deeper depth = better analysis but much slower. Time limit is often easier.
ANALYSIS_TIME_LIMIT = 30 # seconds per move evaluation
ANALYSIS_DEPTH_LIMIT = 25 # Alternative: fixed depth
EARLY_CHECK_TIME = 1 # seconds for preliminary check
EARLY_DEPTH_LIMIT = 15

# Threshold for 'significantly better' (in centipawns)
# How much better the backward knight move must be than the next best alternative
SCORE_THRESHOLD = 300 # e.g., 1.5 pawns

# Maximum number of positions to find before stopping
MAX_POSITIONS = 2000

# Output PGN filename
OUTPUT_PGN_FILENAME = "found_critical_positions.pgn"

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
            "Threads": 8,  # Use 11 physical cores
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

                # --- Rating Check ---
                white_elo_str = game.headers.get("WhiteElo", "0")
                black_elo_str = game.headers.get("BlackElo", "0")

                try:
                    white_elo = int(white_elo_str)
                    black_elo = int(black_elo_str)
                except ValueError:
                    print(f"  Skipping game {game_count}: Invalid Elo rating (White: '{white_elo_str}', Black: '{black_elo_str}')")
                    continue # Skip to the next game

                if white_elo < 2200 or black_elo < 2200:
                    print(f"  Skipping game {game_count}: Elo ratings below threshold (White: {white_elo}, Black: {black_elo})")
                    continue # Skip to the next game
                # --- End Rating Check ---

                board = game.board()
                move_number = 0
                is_white_turn_for_fullmove_counter = True

                node = game # Start from the beginning node
                while node.variations:
                    next_node = node.variations[0]
                    move = next_node.move
                    
                    # Update move number logic
                    current_turn = board.turn # Turn *before* the move is made
                    if current_turn == chess.WHITE:
                        move_number += 1
                    
                    # Correctly display the move being processed
                    if current_turn == chess.WHITE:
                        print(f"  Move {move_number}. {board.san(move)}")
                    else: # current_turn == chess.BLACK
                        print(f"  Move {move_number}... {board.san(move)}")

                    # --- Skip first 10 full moves ---
                    if move_number <= 10:
                        board.push(move)
                        node = next_node
                        continue # Skip analysis for early moves
                    # --- End skip first 10 full moves ---

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
                            best_move = None # Initialize best_move (alternative move, chess.Move object)
                            best_score = None # Initialize best_score (for alternative move in prelim)
                            backward_score = None # Initialize backward_score (for backward move in prelim)

                            # Identify the best alternative move using MultiPV
                            try:
                                analysis_results = engine.analyse(
                                    board,
                                    chess.engine.Limit(time=EARLY_CHECK_TIME, depth=EARLY_DEPTH_LIMIT),
                                    multipv=2  # Get top 2 lines
                                )

                                if not analysis_results:
                                    print("    No analysis results from engine for MultiPV.")
                                    prelim_failed = True
                                else:
                                    # Check PV1
                                    if analysis_results[0]["pv"]:
                                        candidate_move1 = analysis_results[0]["pv"][0]
                                        if candidate_move1.uci() != backward_move_uci:
                                            if candidate_move1 in legal_moves:
                                                best_move = candidate_move1
                                            else:
                                                print(f"    Engine's top move {board.san(candidate_move1)} from PV1 is not legal.")
                                                # prelim_failed will be true if best_move remains None
                                        else:
                                            # PV1 is the backward move, check PV2
                                            if len(analysis_results) > 1 and analysis_results[1]["pv"]:
                                                candidate_move2 = analysis_results[1]["pv"][0]
                                                # Ensure PV2 is not also the backward move (should be different if multipv works as expected)
                                                if candidate_move2.uci() != backward_move_uci:
                                                    if candidate_move2 in legal_moves:
                                                        best_move = candidate_move2
                                                    else:
                                                        print(f"    Engine's top move {board.san(candidate_move2)} from PV2 is not legal.")
                                                else:
                                                    print("    Engine's PV2 also starts with the backward move.")
                                            else:
                                                print("    Engine's top move is backward, but no valid PV2 found for alternative.")
                                    else:
                                        print("    Engine's PV1 is empty.")

                                if not best_move: # If no suitable alternative was found
                                    print("    Could not identify a best alternative move from MultiPV analysis.")
                                    prelim_failed = True

                            except Exception as e:
                                print(f"    Preliminary engine error during MultiPV analysis: {e}")
                                prelim_failed = True

                            # Get score for the identified best alternative move
                            if not prelim_failed and best_move:
                                temp_board_best = board.copy()
                                try:
                                    temp_board_best.push(best_move)
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
                                        print(f"    Engine best alternative move: {board.san(best_move)} (score={best_score}, depth={depth_reached_best})")
                                    else:
                                        print(f"    Engine best alternative move: {board.san(best_move)}: no score, depth={depth_reached_best}")
                                        prelim_failed = True
                                except Exception as e:
                                    print(f"    Error evaluating best alternative move {board.san(best_move)}: {e}")
                                    prelim_failed = True
                            elif not prelim_failed and not best_move: # Should have been caught by prelim_failed = True
                                print("    No best alternative move identified to evaluate (consistency check).")
                                prelim_failed = True


                            # Get score for backward knight move (only if alternative scoring was successful)
                            if not prelim_failed:
                                temp_board_backward = board.copy() # Use a different name to avoid confusion
                                temp_board_backward.push(chess.Move.from_uci(backward_move_uci))
                                try:
                                    info_backward_eval = engine.analyse( # Use a different name
                                        temp_board_backward,
                                        chess.engine.Limit(time=EARLY_CHECK_TIME, depth=EARLY_DEPTH_LIMIT)
                                    )
                                    score_obj_backward_eval = info_backward_eval.get("score", None) # Use a different name
                                    depth_reached_backward_eval = info_backward_eval.get("depth", None) # Use a different name
                                    if score_obj_backward_eval:
                                        if current_turn == chess.WHITE:
                                            backward_score = score_obj_backward_eval.white().score(mate_score=30000)
                                        else:
                                            backward_score = score_obj_backward_eval.black().score(mate_score=30000)
                                        print(f"    Backward move {board.san(chess.Move.from_uci(backward_move_uci))}: score={backward_score}, depth={depth_reached_backward_eval}")
                                    else:
                                        print(f"    Backward move {board.san(chess.Move.from_uci(backward_move_uci))}: no score, depth={depth_reached_backward_eval}")
                                        prelim_failed = True
                                except Exception as e:
                                    print(f"    Preliminary engine error for backward move: {e}")
                                    prelim_failed = True

                            # Compare scores
                            if prelim_failed or backward_score is None or best_score is None: # best_score could be None if best_move was None
                                print(f"    Skipping full analysis: Prelim analysis failed or scores unavailable for backward move {backward_move_uci}")
                                run_full_analysis = False # Ensure it's set if already true from a previous state (though unlikely here)
                            else:
                                # Determine if the backward move was the engine's initial top suggestion (PV1)
                                engine_top_choice_was_backward = False
                                # analysis_results might be None if the initial MultiPV call failed,
                                # but prelim_failed should have caught that. This is an extra safety check.
                                if analysis_results and analysis_results[0].get("pv") and analysis_results[0]["pv"][0].uci() == backward_move_uci:
                                    engine_top_choice_was_backward = True

                                # Core condition: backward move must be significantly better than the best identified alternative.
                                if backward_score >= best_score + SCORE_THRESHOLD:
                                    if engine_top_choice_was_backward:
                                        print(f"    Preliminary check: Backward move (engine's top choice, score {backward_score}) exceeds alternative's score ({best_score}) by threshold ({SCORE_THRESHOLD}).")
                                    else:
                                        # best_move here would be the engine's actual top choice (PV1)
                                        print(f"    Preliminary check: Backward move (score {backward_score}) exceeds engine's top choice ({board.san(best_move)}, score {best_score}) by threshold ({SCORE_THRESHOLD}).")
                                    run_full_analysis = True
                                else:
                                    if engine_top_choice_was_backward:
                                        print(f"    Skipping full analysis: Backward move (engine's top choice, score {backward_score}) does not sufficiently exceed alternative's score ({best_score}). (Required improvement: {SCORE_THRESHOLD})")
                                    else:
                                        print(f"    Skipping full analysis: Backward move (score {backward_score}) does not sufficiently exceed engine's top choice ({board.san(best_move)}, score {best_score}). (Required improvement: {SCORE_THRESHOLD})")
                                    run_full_analysis = False

                            # --- Full Analysis (Only if preliminary check passed) ---
                            if run_full_analysis:
                                print(f"  Running full analysis (Depth={ANALYSIS_DEPTH_LIMIT}, Time={ANALYSIS_TIME_LIMIT}s) for position before {move_number}{'...' if current_turn == chess.BLACK else '.'}{board.san(move)}")
                                
                                backward_move_score_full = None
                                alternative_best_score_full = None
                                analysis_successful = True # Flag for successful analysis of both moves

                                # 1. Analyze the backward knight move (variable 'move')
                                try:
                                    temp_board_backward = board.copy()
                                    temp_board_backward.push(move) # 'move' is the backward knight move
                                    info_backward = engine.analyse(temp_board_backward, chess.engine.Limit(depth=ANALYSIS_DEPTH_LIMIT, time=ANALYSIS_TIME_LIMIT))
                                    score_obj_backward = info_backward.get("score")
                                    depth_reached_backward = info_backward.get("depth")
                                    if score_obj_backward:
                                        if current_turn == chess.WHITE:
                                            backward_move_score_full = score_obj_backward.white().score(mate_score=30000)
                                        else:
                                            backward_move_score_full = score_obj_backward.black().score(mate_score=30000)
                                        print(f"    Full analysis - Backward move {board.san(move)}: score={backward_move_score_full}, depth={depth_reached_backward}")
                                    else:
                                        print(f"    Full analysis - Backward move {board.san(move)}: no score, depth={depth_reached_backward}")
                                        analysis_successful = False # Mark as failed if no score
                                except Exception as e:
                                    print(f"    Full analysis error for backward move {board.san(move)}: {e}")
                                    analysis_successful = False

                                # 2. Analyze the best alternative move (variable 'best_move' from preliminary analysis)
                                # 'best_move' is a chess.Move object for the best alternative.
                                if analysis_successful and best_move: # Proceed only if backward analysis was ok and best_move exists
                                    try:
                                        temp_board_alternative = board.copy()
                                        temp_board_alternative.push(best_move) # 'best_move' is the alternative
                                        info_alternative = engine.analyse(temp_board_alternative, chess.engine.Limit(depth=ANALYSIS_DEPTH_LIMIT, time=ANALYSIS_TIME_LIMIT))
                                        score_obj_alternative = info_alternative.get("score")
                                        depth_reached_alternative = info_alternative.get("depth")
                                        if score_obj_alternative:
                                            if current_turn == chess.WHITE:
                                                alternative_best_score_full = score_obj_alternative.white().score(mate_score=30000)
                                            else:
                                                alternative_best_score_full = score_obj_alternative.black().score(mate_score=30000)
                                            print(f"    Full analysis - Alternative move {board.san(best_move)}: score={alternative_best_score_full}, depth={depth_reached_alternative}")
                                        else:
                                            print(f"    Full analysis - Alternative move {board.san(best_move)}: no score, depth={depth_reached_alternative}")
                                            analysis_successful = False # Mark as failed if no score
                                    except Exception as e:
                                        print(f"    Full analysis error for alternative move {board.san(best_move)}: {e}")
                                        analysis_successful = False
                                elif not best_move and analysis_successful:
                                    print(f"    Skipping alternative move analysis: No best_move identified from prelims.")
                                    analysis_successful = False


                                # 3. Compare scores and record if criteria met
                                if analysis_successful and backward_move_score_full is not None and alternative_best_score_full is not None:
                                    if backward_move_score_full >= alternative_best_score_full + SCORE_THRESHOLD:
                                        move_san = board.san(move) # SAN of the backward knight move
                                        
                                        all_scores_info = {}
                                        all_scores_info[move_san] = backward_move_score_full
                                        if best_move: # best_move might be None if analysis_successful was already false
                                             all_scores_info[board.san(best_move)] = alternative_best_score_full

                                        position_info = {
                                            "headers": game.headers,
                                            "fen_before_move": fen_before_move,
                                            "move_number": move_number,
                                            "turn": "White" if current_turn == chess.WHITE else "Black",
                                            "solution_san": move_san,
                                            "solution_score": backward_move_score_full,
                                            "next_best_score": alternative_best_score_full,
                                            "all_scores" : all_scores_info
                                        }
                                        positions.append(position_info)
                                        print(f"    >>> Found critical backward move: {move_san} (Score: {backward_move_score_full}, Alt Best: {alternative_best_score_full}) ({len(positions)}/{MAX_POSITIONS})")

                                        if len(positions) >= MAX_POSITIONS:
                                            print(f"Reached maximum position limit ({MAX_POSITIONS}). Stopping analysis for this game.")
                                            break 
                                    else:
                                        print(f"    Full analysis: Backward move {board.san(move)} ({backward_move_score_full}) not significantly better than alternative {board.san(best_move)} ({alternative_best_score_full}). Threshold: {SCORE_THRESHOLD}")
                                elif analysis_successful and (backward_move_score_full is None or alternative_best_score_full is None):
                                    # This case means analysis ran but one of the scores was None (already printed by analysis blocks)
                                    print(f"    Skipping position: Full analysis did not yield comparable scores.")
                                elif not analysis_successful:
                                    # This case means an exception occurred or best_move was missing (already printed)
                                    print(f"    Skipping position: Full analysis was not successful.")

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
    print(f"Maximum positions to find: {MAX_POSITIONS}")
    print(f"Output PGN will be saved to: {OUTPUT_PGN_FILENAME}")


    found_positions = find_critical_backward_knight_moves(pgn_path, STOCKFISH_PATH)

    if found_positions:
        print(f"\n--- Analysis Complete ---")
        if len(found_positions) >= MAX_POSITIONS:
             print(f"Found {len(found_positions)} positions (stopped after reaching the limit of {MAX_POSITIONS}).")
        else:
             print(f"Found {len(found_positions)} positions where a backward knight move was significantly better.")

        # Example: Print details of the first 5 found positions
        for i, pos in enumerate(found_positions[:5]): # Still print first 5 to console for quick check
            print(f"\nPosition {i+1}:")
            print(f"  Game: {pos['headers'].get('White', '?')} vs {pos['headers'].get('Black', '?')} ({pos['headers'].get('Event', '?')})")
            print(f"  FEN (before move): {pos['fen_before_move']}")
            print(f"  Turn: {pos['turn']}")
            print(f"  Critical Move (Solution): {pos['move_number']}{'.' if pos['turn'] == 'White' else '...'} {pos['solution_san']}")
            print(f"  Solution Score: {pos['solution_score']}cp")
            print(f"  Next Best Score: {pos['next_best_score']}cp")
            # print(f"  All Move Scores: {pos['all_scores']}") # Uncomment for more detail

        # Save these positions to a new PGN file
        try:
            with open(OUTPUT_PGN_FILENAME, "w", encoding="utf-8") as f:
                exporter = chess.pgn.FileExporter(f)
                for i, pos_data in enumerate(found_positions):
                    game_to_export = chess.pgn.Game()

                    # Copy original headers
                    for key, value in pos_data['headers'].items():
                        game_to_export.headers[key] = value
                    
                    # Set FEN and SetUp for the specific position
                    game_to_export.headers["FEN"] = pos_data['fen_before_move']
                    game_to_export.headers["SetUp"] = "1" # Important for PGN readers to use FEN

                    # Add custom tags for our analysis data
                    game_to_export.headers["CriticalMoveSAN"] = pos_data['solution_san']
                    game_to_export.headers["SolutionScore"] = str(pos_data['solution_score'])
                    game_to_export.headers["NextBestScore"] = str(pos_data['next_best_score'])
                    game_to_export.headers["OriginalMoveNumber"] = str(pos_data['move_number']) # Renamed to avoid PGN move number confusion
                    game_to_export.headers["TurnToPlay"] = pos_data['turn'] # Renamed to avoid confusion with PGN 'PlyCount' or similar

                    # Create a board from FEN to make and add the critical move
                    board_for_pgn = chess.Board(pos_data['fen_before_move'])
                    try:
                        move_obj = board_for_pgn.parse_san(pos_data['solution_san'])
                        game_to_export.add_main_variation(move_obj)
                    except ValueError as e:
                        print(f"Warning: Could not parse SAN '{pos_data['solution_san']}' for FEN '{pos_data['fen_before_move']}' in position {i+1}. Skipping move in PGN. Error: {e}")
                    except Exception as e:
                        print(f"Warning: An unexpected error occurred while adding move for position {i+1}. Skipping move in PGN. Error: {e}")


                    game_to_export.accept(exporter)
            print(f"\nSuccessfully saved {len(found_positions)} positions to {OUTPUT_PGN_FILENAME}")
        except Exception as e:
            print(f"\nError writing to PGN file {OUTPUT_PGN_FILENAME}: {e}")
    else:
        print("\n--- Analysis Complete ---")
        print("No positions meeting the criteria were found.")

    end_time = time.time()
    print(f"\nTotal analysis time: {end_time - start_time:.2f} seconds.")
    # Adding current time as requested in context
    print(f"Script finished at: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
