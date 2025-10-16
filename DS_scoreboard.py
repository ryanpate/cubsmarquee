from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
import statsapi
import time
import pendulum
from datetime import datetime

# Constants
FONT_PATHS = {
    'time_font': './fonts/6x9.bdf',
    'warmup_font': './fonts/9x18B.bdf',
    'batter_font': './fonts/4x6.bdf',
    'lineup_font': './fonts/7x14B.bdf',
    'cubs_score_font': './fonts/9x18B.bdf',
    'count_font': './fonts/5x7.bdf',
    'out_font': './fonts/4x6.bdf',
    'inning_font': './fonts/5x7.bdf',
    'bat_font': './fonts/tom-thumb.bdf',
    'scored_font': './fonts/9x18B.bdf',
    'final_font': './fonts/4x6.bdf',
    'title_font': './fonts/5x8.bdf',
    'standings_font': './fonts/4x6.bdf',
    '10x20_font': './fonts/10x20.bdf',
    '6x13B_font': './fonts/6x13B.bdf'
}

COLORS = {
    'text_color': graphics.Color(255, 255, 255),
    'run_color': graphics.Color(0, 0, 0),
    'final_color': graphics.Color(255, 233, 0),
    'shadow_color': graphics.Color(0, 0, 255),
    'scored_color': graphics.Color(255, 233, 0),
    'scored_shadow_color': graphics.Color(255, 255, 255),
    'title_color': graphics.Color(255, 255, 0),
    'standings_color': graphics.Color(255, 255, 255)
}

TEAM_ID = 112  # Cubs team ID

class Schedule:
    @staticmethod
    def get_schedule():
        """Fetch the schedule for the Cubs."""
        current_date = pendulum.now().format('MM/DD/YYYY')
        schedule = statsapi.schedule(start_date=current_date, team=TEAM_ID)
        if not schedule:
            next_game = statsapi.next_game(teamId=TEAM_ID)
            schedule = statsapi.schedule(game_id=next_game)
        return schedule

    @staticmethod
    def get_pitchers(game_index, game_id):
        """Get the pitchers for a specific game."""
        schedule = Schedule.get_schedule()
        home_pitcher = schedule[game_index]['home_probable_pitcher'] or 'TBD'
        away_pitcher = schedule[game_index]['away_probable_pitcher'] or 'TBD'
        game_data = statsapi.get('game', {'gamePk': game_id})['gameData']['teams']
        away_team_name = game_data['away']['teamName']
        if schedule[game_index]['home_id'] == TEAM_ID:
            return f'Cubs Pitcher: {home_pitcher}    {away_team_name} Pitcher: {away_pitcher}'
        return f'Cubs Pitcher: {away_pitcher}    {away_team_name} Pitcher: {home_pitcher}'

    @staticmethod
    def get_lineup(game_id):
        """Get the lineup for a specific game."""
        game_data = statsapi.get('game', {'gamePk': game_id})['liveData']['boxscore']['teams']
        home_data = game_data['home']['batters']
        home_team = game_data['home']['team']['name']
        away_data = game_data['away']['batters']
        away_team = game_data['away']['team']['name']

        lineup = f'{home_team} - '
        for batter in home_data:
            player_data = statsapi.get('people', {'personIds': batter})['people'][0]
            lineup += f"{player_data['primaryPosition']['abbreviation']}:{player_data['lastName']} "

        lineup += f'  {away_team} - '
        for batter in away_data:
            player_data = statsapi.get('people', {'personIds': batter})['people'][0]
            lineup += f"{player_data['primaryPosition']['abbreviation']}:{player_data['lastName']} "

        return lineup

    @staticmethod
    def get_away_team(game_id):
        """Get the abbreviation of the away team."""
        game_data = statsapi.get('game', {'gamePk': game_id})['gameData']['teams']
        return game_data['away']['abbreviation'] if game_data['home']['id'] == TEAM_ID else game_data['home']['abbreviation']

    @staticmethod
    def get_game_time(game_index):
        """Get the formatted game time."""
        schedule = Schedule.get_schedule()
        game_time = schedule[game_index]['game_datetime'][-9:19]
        if game_time[:2] == '00':
            game_time = '24:' + game_time[3:]
        hour = int(game_time[:2])
        if hour - 5 < 0:
            hour += 7
        else:
            hour -= 5
        if hour > 12:
            hour -= 12
        return f"{hour}{game_time[2:]}"


class DisplayManager:
    def __init__(self):
        """Initialize the RGB matrix and canvas."""
        self.matrix_options = RGBMatrixOptions()
        self.matrix_options.rows = 48
        self.matrix_options.cols = 96
        self.matrix_options.chain_length = 1
        self.matrix_options.parallel = 1
        self.matrix_options.hardware_mapping = 'regular'
        self.matrix = RGBMatrix(options=self.matrix_options)
        self.canvas = self.matrix.CreateFrameCanvas()

    def draw_text(self, text, font, x, y, color):
        """Draw text on the canvas."""
        graphics.DrawText(self.canvas, font, x, y, color, text)

    def clear_canvas(self):
        """Clear the canvas."""
        self.canvas.Clear()

    def swap_canvas(self):
        """Swap the canvas on VSync."""
        self.canvas = self.matrix.SwapOnVSync(self.canvas)


class GameDisplay:
    def __init__(self, display_manager):
        self.display_manager = display_manager

    def warmup(self, game_index, game_id, lineup, images):
        """Display warmup information."""
        schedule = Schedule.get_schedule()
        start_time = Schedule.get_game_time(game_index)
        current_time = pendulum.now().format('HH:MM')
        pos = self.display_manager.canvas.width

        while current_time != start_time[:5] or schedule[game_index]['status'] not in ['In Progress', 'Delayed']:
            self.display_manager.clear_canvas()
            self.display_manager.canvas.Fill(70, 128, 83)
            self.display_manager.draw_text(
                'WARM UP', graphics.Font(), 17, 12, COLORS['text_color'])
            self.display_manager.draw_text(
                'START TIME', graphics.Font(), 17, 24, COLORS['text_color'])
            self.display_manager.draw_text(
                start_time[:4], graphics.Font(), 36, 32, COLORS['text_color'])

            pos -= 1
            text_length = graphics.DrawText(self.display_manager.canvas, graphics.Font(
            ), pos, 45, COLORS['text_color'], lineup)
            if pos + text_length < 0:
                pos = self.display_manager.canvas.width
                lineup = Schedule.get_lineup(game_id)

            self.display_manager.swap_canvas()
            time.sleep(0.02)
            current_time = pendulum.now().format('HH:MM')

        if schedule[game_index]['status'] == 'In Progress':
            self.game_on(game_index, game_id, lineup, images)
        elif schedule[game_index]['status'][:7] == 'Delayed':
            self.delayed(game_index, game_id, lineup, images)

    def game_on(self, game_index, game_id, lineup, images):
        """Display real-time game information."""
        schedule = Schedule.get_schedule()
        cubs_home = schedule[game_index]['home_id'] == TEAM_ID

        # Initialize scores
        cubs_score = schedule[game_index]['home_score'] if cubs_home else schedule[game_index]['away_score']
        opp_score = schedule[game_index]['away_score'] if cubs_home else schedule[game_index]['home_score']

        while True:
            # Fetch live game data
            live_data = statsapi.get('game', {'gamePk': game_id})['liveData']
            linescore = live_data['linescore']
            current_play = live_data['plays']['currentPlay']
            offense = linescore['offense']

            # Update scores
            if cubs_home:
                cubs_score = linescore['teams']['home']['runs']
                opp_score = linescore['teams']['away']['runs']
            else:
                cubs_score = linescore['teams']['away']['runs']
                opp_score = linescore['teams']['home']['runs']

            # Clear canvas and draw background
            self.display_manager.clear_canvas()
            self.display_manager.canvas.Fill(70, 128, 83)  # Green background

            # Draw team logos
            self.display_manager.canvas.SetImage(
                images['cubs_image'].convert("RGB"), 1, 0)
            self.display_manager.canvas.SetImage(
                images['opp_image'].convert("RGB"), 1, 17)

            # Draw scoreboard
            self.draw_scoreboard(cubs_score, opp_score, cubs_home)

            # Draw inning and count
            self.draw_inning_count(linescore, current_play)

            # Draw bases
            self.draw_bases(offense)

            # Draw batter and pitcher information
            self.draw_batter_pitcher(current_play)

            # Swap canvas to update display
            self.display_manager.swap_canvas()

            # Check if the game is over
            if schedule[game_index]['status'] in ['Final', 'Game Over']:
                self.game_over(game_index, game_id, images)
                break

            time.sleep(5)  # Refresh every 5 seconds

    def delayed(self, game_index, game_id, lineup, images):
        """Display delayed game information."""
        schedule = Schedule.get_schedule()
        start_time = Schedule.get_game_time(game_index)
        current_time = pendulum.now().format('HH:MM')
        pos = self.display_manager.canvas.width

        # Load fonts
        warmup_font = graphics.Font()
        warmup_font.LoadFont(FONT_PATHS['warmup_font'])
        time_font = graphics.Font()
        time_font.LoadFont(FONT_PATHS['time_font'])
        lineup_font = graphics.Font()
        lineup_font.LoadFont(FONT_PATHS['lineup_font'])

        while current_time != start_time[:5] or schedule[game_index]['status'] != 'In Progress':
            self.display_manager.clear_canvas()
            # Yellow background for delayed status
            self.display_manager.canvas.Fill(255, 210, 0)

            # Draw "DELAYED" text
            self.display_manager.draw_text(
                'DELAYED', warmup_font, 17, 12, COLORS['text_color'])

            # Draw "START TIME" text
            self.display_manager.draw_text(
                'START TIME', time_font, 17, 24, COLORS['text_color'])

            # Draw the scheduled start time
            self.display_manager.draw_text(
                start_time[:4], time_font, 36, 32, COLORS['text_color'])

            # Scroll the lineup information
            pos -= 1
            text_length = graphics.DrawText(
                self.display_manager.canvas, lineup_font, pos, 45, COLORS['text_color'], lineup)
            if pos + text_length < 0:
                pos = self.display_manager.canvas.width
                lineup = Schedule.get_lineup(game_id)

            # Swap canvas to update display
            self.display_manager.swap_canvas()

            # Check if the game has started
            if schedule[game_index]['status'] == 'In Progress':
                self.game_on(game_index, game_id, lineup, images)
                break

            # Update current time
            current_time = pendulum.now().format('HH:MM')
            time.sleep(0.02)  # Control scroll speed

    def draw_scoreboard(self, cubs_score, opp_score, cubs_home):
        """Draw the scoreboard on the canvas."""
        cubs_score_font = graphics.Font()
        cubs_score_font.LoadFont(FONT_PATHS['cubs_score_font'])

        if cubs_home:
            self.display_manager.draw_text(
                str(cubs_score), cubs_score_font, 20, 13, COLORS['run_color'])
            self.display_manager.draw_text(
                str(opp_score), cubs_score_font, 20, 30, COLORS['run_color'])
        else:
            self.display_manager.draw_text(
                str(cubs_score), cubs_score_font, 20, 13, COLORS['run_color'])
            self.display_manager.draw_text(
                str(opp_score), cubs_score_font, 20, 30, COLORS['run_color'])

    def draw_inning_count(self, linescore, current_play):
        """Draw the current inning and count."""
        inning_font = graphics.Font()
        inning_font.LoadFont(FONT_PATHS['inning_font'])

        inning_state = linescore['inningState'][:3]  # Top, Mid, Bot, End
        inning_number = linescore['currentInningOrdinal']
        count = f"{current_play['count']['balls']
                   } - {current_play['count']['strikes']}"

        self.display_manager.draw_text(
            inning_state, inning_font, 76, 9, COLORS['text_color'])
        self.display_manager.draw_text(
            inning_number, inning_font, 76, 19, COLORS['text_color'])
        self.display_manager.draw_text(
            count, inning_font, 39, 31, COLORS['text_color'])

    def draw_bases(self, offense):
        """Draw the base status (runners on base)."""
        base_positions = {
            'first_base': (46 + 7, 8 + 7),
            'second_base': (46, 8),
            'third_base': (46 - 7, 8 + 7)
        }

        for base, (x, y) in base_positions.items():
            if offense.get(base, False):
                self.draw_base(x, y, filled=True)
            else:
                self.draw_base(x, y, filled=False)

    def draw_base(self, x, y, filled):
        """Draw a single base on the canvas."""
        color = (255, 255, 255) if filled else (0, 51, 102)
        for i in range(5):
            self.display_manager.canvas.SetPixel(x + i, y, *color)
            self.display_manager.canvas.SetPixel(x + i, y - 1, *color)
            self.display_manager.canvas.SetPixel(x + i, y - 2, *color)

    def draw_batter_pitcher(self, current_play):
        """Draw the batter and pitcher information."""
        batter_font = graphics.Font()
        batter_font.LoadFont(FONT_PATHS['batter_font'])

        batter_name = current_play['matchup']['batter']['fullName']
        pitcher_name = current_play['matchup']['pitcher']['fullName']

        self.display_manager.draw_text(
            f"BAT: {batter_name}", batter_font, 2, 46, COLORS['run_color'])
        self.display_manager.draw_text(
            f"PIT: {pitcher_name}", batter_font, 2, 38, COLORS['run_color'])

    def game_over(self, game_index, game_id, images):
        """Display the game over screen with final results."""
        schedule = Schedule.get_schedule()
        current_date = pendulum.now().format('YYYY-MM-DD')
        current_time = pendulum.now().format('HH:MM')

        # Fetch game data
        game_data = statsapi.get('game', {'gamePk': game_id})['liveData']
        linescore = game_data['linescore']
        boxscore = game_data['boxscore']['teams']

        # Determine if Cubs are home or away
        cubs_home = schedule[game_index]['home_id'] == TEAM_ID

        # Get final scores
        if cubs_home:
            cubs_score = boxscore['home']['teamStats']['batting']['runs']
            opp_score = boxscore['away']['teamStats']['batting']['runs']
        else:
            cubs_score = boxscore['away']['teamStats']['batting']['runs']
            opp_score = boxscore['home']['teamStats']['batting']['runs']

        # Get game stats
        innings = linescore['currentInning']
        hits = boxscore['home']['teamStats']['batting']['hits'] if cubs_home else boxscore['away']['teamStats']['batting']['hits']
        runs = cubs_score
        errors = boxscore['home']['teamStats']['fielding']['errors'] if cubs_home else boxscore['away']['teamStats']['fielding']['errors']

        # Load fonts
        final_font = graphics.Font()
        final_font.LoadFont(FONT_PATHS['final_font'])
        cubs_score_font = graphics.Font()
        cubs_score_font.LoadFont(FONT_PATHS['10x20_font'])
        inning_font = graphics.Font()
        inning_font.LoadFont(FONT_PATHS['6x13B_font'])

        # Display final results
        while current_date == pendulum.now().format('YYYY-MM-DD') and current_time != '04:00':
            self.display_manager.clear_canvas()
            self.display_manager.canvas.Fill(0, 0, 0)  # Black background

            # Draw "GAME OVER" text
            self.display_manager.draw_text(
                'GAME', inning_font, 36, 11, COLORS['final_color'])
            self.display_manager.draw_text(
                'OVER', inning_font, 36, 21, COLORS['final_color'])

            # Draw game stats
            self.display_manager.draw_text(
                f'INNINGS: {innings}', final_font, 29, 29, COLORS['final_color'])
            self.display_manager.draw_text(
                f'HITS:   {hits}', final_font, 29, 35, COLORS['final_color'])
            self.display_manager.draw_text(
                f'RUNS:   {runs}', final_font, 29, 41, COLORS['final_color'])
            self.display_manager.draw_text(
                f'ERRORS: {errors}', final_font, 29, 47, COLORS['final_color'])

            # Draw final scores
            self.display_manager.draw_text(
                str(cubs_score), cubs_score_font, 5, 44, COLORS['shadow_color'])
            self.display_manager.draw_text(
                str(cubs_score), cubs_score_font, 6, 45, COLORS['run_color'])
            self.display_manager.draw_text(
                str(opp_score), cubs_score_font, 70, 44, COLORS['shadow_color'])
            self.display_manager.draw_text(
                str(opp_score), cubs_score_font, 71, 45, COLORS['run_color'])

            # Swap canvas to update display
            self.display_manager.swap_canvas()

            # Check if it's time to transition to the next game or standings
            current_date = pendulum.now().format('YYYY-MM-DD')
            current_time = pendulum.now().format('HH:MM')
            time.sleep(5)  # Refresh every 5 seconds

        # Transition to the next game or standings
        if schedule[game_index]['doubleheader'] == 'S':
            time.sleep(360)  # Wait 6 minutes before starting the next game
            self.startup()
        else:
            self.display_standings()

    def display_standings(self):
        """Display division standings."""
        standings = statsapi.get('standings', {'leagueId': 104})[
            'records'][1]['teamRecords']
        title_font = graphics.Font()
        title_font.LoadFont(FONT_PATHS['title_font'])
        standings_font = graphics.Font()
        standings_font.LoadFont(FONT_PATHS['standings_font'])

        self.display_manager.clear_canvas()
        self.display_manager.canvas.Fill(70, 128, 83)  # Green background

        # Draw "DIVISION STANDINGS" title
        self.display_manager.draw_text(
            'DIVISION STANDINGS', title_font, 3, 8, COLORS['title_color'])

        # Draw standings
        standings_y = 15
        for team in standings:
            team_abv = statsapi.get('team', {'teamId': team['team']['id']})[
                'teams'][0]['abbreviation']
            record = f"{team['leagueRecord']['wins']}-{team['leagueRecord']
                                                       ['losses']} {team['leagueRecord']['pct']}"
            games_back = team['gamesBack'] if team['gamesBack'] != '-' else ''
            self.display_manager.draw_text(
                team_abv, standings_font, 5, standings_y, COLORS['standings_color'])
            self.display_manager.draw_text(
                record, standings_font, 26, standings_y, COLORS['standings_color'])
            self.display_manager.draw_text(
                games_back, standings_font, 75, standings_y, COLORS['standings_color'])
            standings_y += 8

        # Swap canvas to update display
        self.display_manager.swap_canvas()
        time.sleep(15)  # Display standings for 15 seconds

    def startup(self):
        """Start the display loop for the next game."""
        schedule = Schedule.get_schedule()
        game_index = 0
        game_id = schedule[game_index]['game_id']
        lineup = Schedule.get_lineup(game_id)
        images = {
            'opp_image': Image.open(f"./logos/{Schedule.get_away_team(game_id)}.png"),
            'cubs_image': Image.open("./logos/cubs.png"),
            'batting_image': Image.open("./baseball.png")
        }

        if schedule[game_index]['status'] == 'Scheduled':
            self.warmup(game_index, game_id, lineup, images)
        elif schedule[game_index]['status'] in ['Warmup', 'Pre-Game']:
            self.warmup(game_index, game_id, lineup, images)
        elif schedule[game_index]['status'][:7] == 'Delayed':
            self.delayed(game_index, game_id, lineup, images)
        elif schedule[game_index]['status'] == 'In Progress':
            self.game_on(game_index, game_id, lineup, images)
        elif schedule[game_index]['status'] in ['Final', 'Game Over']:
            self.game_over(game_index, game_id, images)

def main():
    display_manager = DisplayManager()
    game_display = GameDisplay(display_manager)

    schedule = Schedule.get_schedule()
    game_index = 0
    game_id = schedule[game_index]['game_id']
    lineup = Schedule.get_lineup(game_id)
    images = {
        'opp_image': Image.open(f"./logos/{Schedule.get_away_team(game_id)}.png"),
        'cubs_image': Image.open("./logos/cubs.png"),
        'batting_image': Image.open("./baseball.png")
    }

    if schedule[game_index]['status'] == 'Scheduled':
        game_display.warmup(game_index, game_id, lineup, images)
    elif schedule[game_index]['status'] in ['Warmup', 'Pre-Game']:
        game_display.warmup(game_index, game_id, lineup, images)
    elif schedule[game_index]['status'][:7] == 'Delayed':
        game_display.delayed(game_index, game_id, lineup, images)
    elif schedule[game_index]['status'] == 'In Progress':
        game_display.game_on(game_index, game_id, lineup, images)
    elif schedule[game_index]['status'] in ['Final', 'Game Over']:
        game_display.game_over(game_index, game_id, images)
        pass

if __name__ == "__main__":
    main()