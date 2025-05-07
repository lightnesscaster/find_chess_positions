\
import chess.pgn
import io

def filter_puzzles(input_pgn_path, output_pgn_path, score_threshold=-200):
    """
    Filters puzzles from a PGN file based on the SolutionScore.

    Args:
        input_pgn_path (str): Path to the input PGN file.
        output_pgn_path (str): Path to save the filtered PGN file.
        score_threshold (int): The minimum SolutionScore to keep a puzzle.
    """
    filtered_games = []
    count = 0
    with open(input_pgn_path) as pgn_file:
        while True:
            game = chess.pgn.read_game(pgn_file)
            if game is None:
                break

            solution_score_str = game.headers.get("SolutionScore")
            if solution_score_str:
                try:
                    solution_score = int(solution_score_str)
                    # Check whose turn it is to determine if the score needs to be inverted
                    # FEN string's second part indicates active color ('w' or 'b')
                    fen = game.headers.get("FEN")
                    if fen:
                        turn = fen.split()[1]
                        # If it's Black to move, the score is from Black's perspective.
                        # A positive score for Black is good for Black.
                        # A negative score for White is good for Black.
                        # The "SolutionScore" seems to be from the perspective of the side to move.
                        # So, if it's white to move and score is > -200 (e.g., -100, 0, 100), it's good for white.
                        # If it's black to move and score is > -200 (e.g., -100, 0, 100), it's good for black.
                        # No inversion needed based on this interpretation.
                        if solution_score > score_threshold:
                            filtered_games.append(game)
                        else:
                            count += 1
                except ValueError:
                    print(f"Warning: Could not parse SolutionScore '{solution_score_str}' for a game.")
            else:
                print("Warning: Game missing SolutionScore header.")

    with open(output_pgn_path, "w", encoding="utf-8") as output_file:
        for game in filtered_games:
            exporter = chess.pgn.FileExporter(output_file)
            game.accept(exporter)

    print(f"Filtered {count} puzzles with SolutionScore <= {score_threshold}.")
    print(f"Filtered PGN saved to {output_pgn_path}")

if __name__ == "__main__":
    input_file = "backwards_knight_puzzles.pgn"
    output_file = "filtered_backwards_knight_puzzles.pgn"
    filter_puzzles(input_file, output_file)
