"""Local test script to compile the Jinja template into a static HTML file."""

import os
from jinja2 import Environment, FileSystemLoader

def build_preview():
    # Set up Jinja to look in the current directory
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('bracket_template.html.j2')

    # This is the mock data your bot's database helper will eventually provide
    mock_data = {
        "tournament_title": "MEGA HALLYU MADNESS: 64-TRACK SHOWDOWN",
        "total_rounds": 6,
        "left_rounds": [
            # Round 1 Left (16 matches)
            [
                {"a_seed": "1", "a_name": "Into The New World", "b_seed": "64", "b_name": "Sticker"},
                {"a_seed": "32", "a_name": "Love Scenario", "b_seed": "33", "b_name": "Shine"},
                {"a_seed": "16", "a_name": "Bad Boy", "b_seed": "49", "b_name": "Lilac"},
                {"a_seed": "17", "a_name": "Blood Sweat & Tears", "b_seed": "48", "b_name": "God's Menu"},
                {"a_seed": "8", "a_name": "Gee", "b_seed": "57", "b_name": "Pop!"},
                {"a_seed": "25", "a_name": "DDU-DU DDU-DU", "b_seed": "40", "b_name": "Tomboy"},
                {"a_seed": "9", "a_name": "Sorry, Sorry", "b_seed": "56", "b_name": "Energetic"},
                {"a_seed": "24", "a_name": "Next Level", "b_seed": "41", "b_name": "Eleven"},
                {"a_seed": "4", "a_name": "Haru Haru", "b_seed": "61", "b_name": "Maniac"},
                {"a_seed": "29", "a_name": "Growl", "b_seed": "36", "b_name": "Love Dive"},
                {"a_seed": "13", "a_name": "I Am The Best", "b_seed": "52", "b_name": "Wannabe"},
                {"a_seed": "20", "a_name": "Spring Day", "b_seed": "45", "b_name": "Antifragile"},
                {"a_seed": "5", "a_name": "Mirotic", "b_seed": "60", "b_name": "Super Shy"},
                {"a_seed": "28", "a_name": "Fancy", "b_seed": "37", "b_name": "Hype Boy"},
                {"a_seed": "12", "a_name": "Fantastic Baby", "b_seed": "53", "b_name": "Fearless"},
                {"a_seed": "21", "a_name": "Dynamite", "b_seed": "44", "b_name": "Ditto"}
            ],
            # Round 2 Left (8 matches)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""} for _ in range(8)],
            # Round 3 Left (4 matches)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""} for _ in range(4)],
            # Round 4 Left (2 matches)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""} for _ in range(2)],
            # Round 5 Left (1 match)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""}]
        ],
        "right_rounds": [
            # Round 1 Right (16 matches)
            [
                {"a_seed": "2", "a_name": "Ring Ding Dong", "b_seed": "63", "b_name": "Zimzalabim"},
                {"a_seed": "31", "a_name": "Cheer Up", "b_seed": "34", "b_name": "Bboom Bboom"},
                {"a_seed": "15", "a_name": "Psycho", "b_seed": "50", "b_name": "Eight"},
                {"a_seed": "18", "a_name": "Boy With Luv", "b_seed": "47", "b_name": "Thunderous"},
                {"a_seed": "7", "a_name": "Nobody", "b_seed": "58", "b_name": "Gotta Go"},
                {"a_seed": "26", "a_name": "Kill This Love", "b_seed": "39", "b_name": "Queencard"},
                {"a_seed": "10", "a_name": "Lucifer", "b_seed": "55", "b_name": "Crown"},
                {"a_seed": "23", "a_name": "Savage", "b_seed": "42", "b_name": "After Like"},
                {"a_seed": "3", "a_name": "Lies", "b_seed": "62", "b_name": "S-Class"},
                {"a_seed": "30", "a_name": "Call Me Baby", "b_seed": "35", "b_name": "I AM"},
                {"a_seed": "14", "a_name": "Fire", "b_seed": "51", "b_name": "Dalla Dalla"},
                {"a_seed": "19", "a_name": "Fake Love", "b_seed": "46", "b_name": "Unforgiven"},
                {"a_seed": "6", "a_name": "Fiction", "b_seed": "59", "b_name": "ETA"},
                {"a_seed": "27", "a_name": "Feel Special", "b_seed": "38", "b_name": "OMG"},
                {"a_seed": "11", "a_name": "Bang Bang Bang", "b_seed": "54", "b_name": "Blue Hour"},
                {"a_seed": "22", "a_name": "Butter", "b_seed": "43", "b_name": "Supernova"}
            ],
            # Round 2 Right (8 matches)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""} for _ in range(8)],
            # Round 3 Right (4 matches)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""} for _ in range(4)],
            # Round 4 Right (2 matches)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""} for _ in range(2)],
            # Round 5 Right (1 match)
            [{"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""}]
        ],
        "finals": {"a_seed": "", "a_name": "", "b_seed": "", "b_name": ""},
        "winner": ""
    }

    # Render the HTML string
    rendered_html = template.render(mock_data)

    # Save it to a file you can open in your browser
    output_path = 'preview.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(rendered_html)

    print(f"✅ Success! Open {os.path.abspath(output_path)} in your web browser.")

if __name__ == "__main__":
    build_preview()
