import mlbstatsapi
from datetime import datetime

mlb = mlbstatsapi.Mlb()
cubs_0 = 0
current_date = datetime.today().strftime('%Y-%m-%d')
total_home_score = 0
total_away_score = 0

schedule = mlb.get_schedule(current_date)
dates = schedule.dates

for date in dates:
    for game in date.games:
        team_home = game.teams.home.team.name
        team_away = game.teams.away.team.name
        if team_home == 'Chicago Cubs':
            print(team_away + ' @ ' + team_home)
            game_id = game.gamepk
            cubs_on = 1
        elif team_away == 'Chicago Cubs':
            print(team_away + ' @ ' + team_home)
            game_id = game.gamepk
            cubs_on = 1
#        print(game.teams)(game)
#        print(game_id, team_home, team_away)

home_name_length = len(team_home)
away_team_length = len(team_away)
line_score = mlb.get_game_line_score(game_id)
live_game = mlb.get_game(game_id)

#live_game = mlb.get_game(game_id)
#print(live_game)

for score in line_score.innings:
    if str(score.away.runs) == 'None':
        away_team_runs = '0'
    elif str(score.home.runs) == 'None':
        home_team_runs = '0'
    else:
        away_team_runs = str(score.away.runs)
        home_team_runs = str(score.home.runs)
    total_away_score = total_away_score + int(away_team_runs)
    total_home_score = total_home_score + int(home_team_runs)

if cubs_on == 1:
    print(' ' * int((away_team_length) / 2) + str(total_away_score) + ' ' * int(((away_team_length / 2) + (home_name_length / 2))) + str(total_home_score))
#    print(score)
#    print(score.home.runs)
print(schedule)
