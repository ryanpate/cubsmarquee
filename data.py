import statsapi

next_game = statsapi.next_game(teamId=112)
# datetime.today().strftime('%m/%d/%Y')
sched = statsapi.schedule(start_date="03/21/2025", team=112)
#sched = statsapi.schedule(game_id=next_game)
print(next_game)
print(sched)