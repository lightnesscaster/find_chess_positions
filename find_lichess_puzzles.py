import csv
import chess  # You'll need to install python-chess: pip install python-chess
import random  # Added for random position selection

def filter_puzzles(csv_filepath, min_rating, max_rating, desired_themes=None, excluded_themes=None, max_puzzles=None):
    # First, count the total rows to determine the dataset length
    with open(csv_filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        total_rows = sum(1 for _ in reader)
    
    if total_rows == 0:
        print("CSV file is empty or contains only a header.")
        return []
    
    # Generate a random starting point
    random_start = random.randint(1, total_rows)
    print(f"Random start position: {random_start} of {total_rows} puzzles")
    
    # Determine if we should go backward or forward
    go_backward = random_start > total_rows // 2
    
    # Define the processing order based on direction
    if go_backward:
        print(f"Processing backward from position {random_start}")
        # First process from beginning to random_start-1, then from random_start to end
        segments = [
            (1, random_start - 1),        # First segment: beginning to random_start-1
            (random_start, total_rows)    # Second segment: random_start to end
        ]
    else:
        print(f"Processing forward from position {random_start}")
        # First process from random_start to end, then from beginning to random_start-1
        segments = [
            (random_start, total_rows),  # First segment: random_start to end
            (1, random_start - 1)        # Second segment: beginning to random_start-1
        ]
    
    selected_puzzles = []
    count = 0
    processed = 0
    
    # Process each segment
    for start_row, end_row in segments:
        with open(csv_filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Skip to the start of the current segment
            for _ in range(start_row - 1):
                next(reader, None)
            
            # Process rows in this segment
            for i, row in enumerate(reader, start=start_row):
                if i > end_row:
                    break
                
                processed += 1
                try:
                    rating = int(row['Rating'])
                    puzzle_id = row['PuzzleId']
                    fen = row['FEN']
                    moves = row['Moves']
                    themes = row['Themes'].split(' ') # Get themes as a list

                    # --- Your Filtering Logic ---
                    if not (min_rating <= rating <= max_rating):
                        continue # Skip if not in desired rating range

                    # Theme filtering (example)
                    if desired_themes:
                        if not any(theme in themes for theme in desired_themes):
                            continue
                    if excluded_themes:
                        if any(theme in themes for theme in excluded_themes):
                            continue

                    # Apply first move to get the actual puzzle position
                    board = chess.Board(fen)
                    moves_list = moves.split(' ')
                    
                    if moves_list:
                        # Apply the first move to get the position right before the puzzle
                        first_move = chess.Move.from_uci(moves_list[0])
                        board.push(first_move)
                        
                        # Get the new FEN and remaining moves
                        new_fen = board.fen()
                        remaining_moves = ' '.join(moves_list[1:])
                        
                        # Update FEN and moves for this puzzle
                        fen = new_fen
                        moves = remaining_moves

                    # Add more filters if needed (e.g., NbPlays, Popularity)
                    
                    selected_puzzles.append({
                        'PuzzleId': puzzle_id,
                        'FEN': fen,
                        'Moves': moves,
                        'Rating': rating,
                        'Themes': themes
                    })
                    count += 1
                    if max_puzzles and count >= max_puzzles:
                        return selected_puzzles
                    if processed % 10000 == 0: # Optional: print progress
                        print(f"Processed {processed} puzzles, found {count} matching criteria...")

                except ValueError:
                    print(f"Skipping row due to data conversion error: {row}")
                except Exception as e:
                    print(f"An error occurred processing row: {row}, Error: {e}")
                
                # If we've found enough puzzles, stop processing
                if max_puzzles and count >= max_puzzles:
                    break
    
    return selected_puzzles

def export_to_pgn(puzzles, pgn_filepath):
    with open(pgn_filepath, 'w', encoding='utf-8') as f:
        for puzzle in puzzles:
            puzzle_id = puzzle['PuzzleId']
            fen = puzzle['FEN']
            moves_solution_uci = puzzle['Moves'] # Space-separated UCI moves
            rating = puzzle['Rating']
            themes_list = puzzle['Themes']
            themes_str = " ".join(themes_list)

            uci_moves_list = moves_solution_uci.split(' ')

            # Create a board from the FEN
            board = chess.Board(fen)

            # PGN Headers
            f.write(f'[Event "Lichess Puzzle {puzzle_id}"]\n')
            f.write(f'[Site "https://lichess.org/training/{puzzle_id}"]\n')
            f.write('[Date "????.??.??"]\n')
            f.write('[Round "-"]\n')
            f.write('[White "?"]\n')
            f.write('[Black "?"]\n')
            f.write('[Result "*"]\n')
            f.write(f'[FEN "{fen}"]\n')
            f.write('[SetUp "1"]\n')
            f.write(f'[Rating "{rating}"]\n')
            f.write(f'[Themes "{themes_str}"]\n')
            f.write(f'[PlyCount "{len(uci_moves_list)}"]\n')
            
            fen_parts = fen.split(' ')
            turn = fen_parts[1]  # 'w' or 'b'
            turn_to_play_str = "White" if turn == 'w' else "Black"
            f.write(f'[TurnToPlay "{turn_to_play_str}"]\n') # Added TurnToPlay tag
            
            # Movetext generation
            start_move_number = int(fen_parts[5]) 
            
            movetext = "\n"

            if turn == 'w':
                current_m_num_for_pgn = start_move_number
                for i, uci_move in enumerate(uci_moves_list):
                    # Convert UCI move to SAN
                    move = chess.Move.from_uci(uci_move)
                    san_move = board.san(move)
                    
                    if i % 2 == 0:  # White's move
                        movetext += f"{current_m_num_for_pgn}. {san_move} "
                    else:  # Black's move
                        movetext += f"{san_move} "
                        current_m_num_for_pgn += 1
                    
                    board.push(move)  # Update the board
            else:  # Black's turn ('b')
                current_m_num_for_pgn = start_move_number
                
                # First move (Black's)
                move = chess.Move.from_uci(uci_moves_list[0])
                san_move = board.san(move)
                movetext += f"{current_m_num_for_pgn}... {san_move} "
                board.push(move)  # Update the board
                
                if len(uci_moves_list) > 1:
                    for i, uci_move in enumerate(uci_moves_list[1:]):
                        move = chess.Move.from_uci(uci_move)
                        san_move = board.san(move)
                        
                        if i % 2 == 0:  # White's move in sequence
                            current_m_num_for_pgn += 1
                            movetext += f"{current_m_num_for_pgn}. {san_move} "
                        else:  # Black's move in sequence
                            movetext += f"{san_move} "
                        
                        board.push(move)  # Update the board
            
            movetext += "*" # Game termination marker
            f.write(f"{movetext}\n\n") # Add a blank line between PGNs
    print(f"Exported {len(puzzles)} puzzles to {pgn_filepath}")

# --- How to use it ---
if __name__ == "__main__":
    # Replace with the actual path to your decompressed CSV file
    lichess_csv_file = 'lichess_db_puzzle.csv'
    pgn_output_file = 'lichess_puzzles.pgn' # Output PGN filename

    # Define your criteria
    min_target_rating = 1400
    max_target_rating = 1800
    
    # Desired number of puzzles
    num_puzzles_to_find = 600

    # Example: Exclude puzzles that are ONLY tagged as mateIn1 if you want more complex ones
    # themes_to_exclude = ["mateIn1"] 
    themes_to_exclude = None # Or your specific list

    # Example: If you wanted only puzzles with a "fork" or "pin"
    # themes_to_include = ["fork", "pin"]
    themes_to_include = None # Or your specific list


    print(f"Starting puzzle filtering from {lichess_csv_file}...")
    filtered_puzzles = filter_puzzles(
        lichess_csv_file, 
        min_target_rating, 
        max_target_rating, 
        desired_themes=themes_to_include,
        excluded_themes=themes_to_exclude,
        max_puzzles=num_puzzles_to_find
    )

    print(f"\nFound {len(filtered_puzzles)} puzzles matching your criteria.")

    if filtered_puzzles:
        export_to_pgn(filtered_puzzles, pgn_output_file)
    else:
        print("No puzzles found matching criteria, PGN file not created.")

    # Example: Print first 5 found (optional)
    # for i, puzzle in enumerate(filtered_puzzles[:5]): 
    #     print(f"Puzzle {i+1}: ID={puzzle['PuzzleId']}, Rating={puzzle['Rating']}")
