import statsapi, time, os
from datetime import datetime

sched = statsapi.schedule(start_date='08/20/2024', team=112)
#next_sched = game_data.get_sched()
gameid = sched[0]['game_id']
teamid = statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['away']['teamName']
data = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['home']['players']
data2 = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['away']['pitchers']
livedata = statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['strikes']
plays = statsapi.get('game_content', {'gamePk':gameid})
#team = statsapi.next_game(teamId=112)
#standings = statsapi.standings_data(leagueId=104,date='07/21/2023')[205]['teams']

for x in data:
    print(x)