import discord

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from time import sleep
from random import sample


class ScoreDocument:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        self.SPREADSHEET_ID = '11a_dWjSM0ikum4ZpmQ-zLVd_OoIargE8a81qx2q-IcU'

        self.credentials = None
        if os.path.exists('token.json'):
            self.credentials = Credentials.from_authorized_user_file('token.json', self.SCOPES)
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
                self.credentials = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(self.credentials.to_json())

        try:
            self.service = build('sheets', 'v4', credentials=self.credentials)
            self.sheet = self.service.spreadsheets()

        except HttpError as err:
            print(err)

    def read_range(self, sheet_range):
        result = self.sheet.values().get(spreadsheetId=self.SPREADSHEET_ID, range=sheet_range).execute()
        values = result.get('values', [])

        if not values:
            print('No data found')
            return

        return values

    def write_range(self, sheet_range, values):
        self.sheet.values().update(
            spreadsheetId=self.SPREADSHEET_ID,
            valueInputOption='RAW',
            range=sheet_range,
            body=dict(
                majorDimension='ROWS',
                values=values
            )
        ).execute()


class Player:
    def __init__(self, name, score, games_played, imposter_wins, teammate_wins):
        self.name = name
        self.score = score
        self.games_played = games_played
        self.imposter_wins = imposter_wins
        self.teammate_wins = teammate_wins
        self.imposter = False

    def get_sheet_data(self):
        return [self.name, self.score, self.games_played, self.imposter_wins, self.teammate_wins]

    def score(self, winning_team, suspected_imposters):
        self.games_played += 1
        if self.imposter and winning_team and self.name not in suspected_imposters:  # undiscovered successful imposter
            self.imposter_wins += 1
            self.score += 2
        elif self.imposter and winning_team and self.name in suspected_imposters:  # discovered successful imposter
            self.imposter_wins += 1
            self.score += 1
        # ...


class Team:
    def __init__(self, name, imposter_count):
        self.name = name
        self.players = []
        self.imposter_count = imposter_count

    def set_players(self, players, exempt_players):
        self.players = [player for player in players if player not in exempt_players]

    def score(self, winning_team_name, suspected_imposters):
        winning_team = self.name == winning_team_name
        for player in self.players:
            player.score(winning_team, suspected_imposters)

    def assign_imposters(self):
        for player in self.players:
            player.imposter = False

        imposter_players = sample(self.players, self.imposter_count)
        for imposter_player in imposter_players:
            imposter_player.imposter = True


class Game:
    score_document = None
    player_info = None
    exempt_player_list = []
    player_list = []
    teams = []

    @staticmethod
    def create():
        Game.score_document = ScoreDocument()
        Game.player_info = Game.score_document.read_range('A2:E30')

        for name, score, games_played, imposter_wins, teammate_wins in Game.player_info:
            Game.player_list.append(Player(name, score, games_played, imposter_wins, teammate_wins))

    @staticmethod
    def exempt_players(players):
        Game.exempt_player_list.extend(players)

    @staticmethod
    def unexempt_players(players):
        for player in players:
            Game.exempt_player_list.remove(player)

    @staticmethod
    def create_team(team_name, imposter_count):
        Game.teams.append(Team(team_name, imposter_count))

    @staticmethod
    def get_player(player_name):
        if not any(player.name == player_name for player in Game.player_list):
            Game.player_list.append(Player(player_name, 0, 0, 0, 0))
        return [player for player in Game.player_list if player.name == player_name][0]

    @staticmethod
    def get_players(player_names, include_exempt=False):
        players = [Game.get_player(player_name) for player_name in player_names]
        if not include_exempt:
            players = [player for player in players if player not in Game.exempt_player_list]
        return players

    @staticmethod
    def update_players(team_name, player_names):
        if not any(team.name == team_name for team in Game.teams):
            Game.teams.append(Team(team_name))

        team = [team for team in Game.teams if team.name == team_name][0]
        players = Game.get_players(player_names)
        team.set_players(players, Game.exempt_player_list)

    @staticmethod
    def assign_imposters():
        for team in Game.teams:
            team.assign_imposters()


class Client(discord.Client):
    async def get_channel_by_name(self, name):
        channel = discord.utils.get(self.get_all_channels(), name=name)
        return channel

    async def get_users_in_voice_channel(self, channel):
        users = [await self.fetch_user(user_id) for user_id in channel.voice_states.keys()]
        return users

    async def on_ready(self):
        """run on connection to server"""
        print(f'Logged on as {self.user}')

    async def on_message(self, message):
        """run on message in server or to bot"""
        if message.content.startswith('!changeling'):
            print(f'{message.author} said in {message.channel} | {message.content}')

            command = message.content.split()[1:]
            if len(command) == 0:
                await message.channel.send('Command has no args, use `!changeling -h` for help.')

            if command[0] == 'create_team':
                team_name = command[1]

                imposter_count = 0
                if len(command) == 3:
                    imposter_count = int(command[2])

                Game.create_team(team_name, imposter_count)
                discord_users = await self.get_users_in_voice_channel(await self.get_channel_by_name(team_name))
                player_names = [discord_user.name for discord_user in discord_users]
                Game.update_players(team_name, player_names)

                for team in Game.teams:
                    for player in team.players:
                        print('------------------------------------')
                        print(f'{player.name} | {player.score} | {player.imposter_wins} | {player.teammate_wins} | {player.games_played}')

            elif command[0] == 'update_team':
                team_name = command[1]
                discord_users = await self.get_users_in_voice_channel(await self.get_channel_by_name(team_name))
                player_names = [discord_user.name for discord_user in discord_users]
                Game.update_players(team_name, player_names)

                for team in Game.teams:
                    for player in team.players:
                        print('------------------------------------')
                        print(f'{player.name} | {player.score} | {player.imposter_wins} | {player.teammate_wins} | {player.games_played}')

            elif command[0] == 'exempt_player':
                names = command[1:]
                players = Game.get_players(names)
                Game.exempt_players(players)
                print(Game.exempt_player_list)

            elif command[0] == 'include_player':
                names = command[1:]
                players = Game.get_players(names, include_exempt=True)
                Game.unexempt_players(players)
                print(Game.exempt_player_list)

            elif command[0] == 'start':
                report_delay = int(command[1].split(':')[1]) * 60 + int(command[1].split(':')[0])
                sleep(report_delay)
                Game.assign_imposters()

                for team in Game.teams:
                    print(f'Team {team.name} players:')
                    for player in team.players:
                        print(f'    {player.name} is {"not" if not player.imposter else ""}the imposter')

                # todo: stopping and voting things


def main():
    Game.create()
    for player in Game.player_list:
        print(f'{player.name} | {player.score} | {player.imposter_wins} | {player.teammate_wins} | {player.games_played}')
    client = Client()
    client.run('ODMyNDI1MzIzNDg0MjgyOTMw.YHjmfg.HyA6wir8yQnU4WVG2Q9WzanyYHc')


if __name__ == '__main__':
    main()
