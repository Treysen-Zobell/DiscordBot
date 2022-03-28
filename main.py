import discord

import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class ScoreDocument:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        self.SPREADSHEET_ID = '11a_dWjSM0ikum4ZpmQ-zLVd_OoIargE8a81qx2q-IcU'

        self.creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)
        if not self.creds or not creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(self.creds.to_json())

        try:
            self.service = build('sheets', 'v4', credentials=self.creds)
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
    def __init__(self, team_name):
        self.team_name = team_name
        self.exempt_players = []
        self.players = []

    def set_players(self, players):
        self.players = [player for player in players if player not in self.exempt_players]

    def exempt_players(self, players):
        self.exempt_players.extend(players)

    def unexempt_players(self, players):
        self.exempt_players = [player for player in self.players if player not in players]

    def score(self, winning_team_name, suspected_imposters):
        winning_team = self.team_name == winning_team_name
        for player in self.players:
            player.score(winning_team, suspected_imposters)


class Game:
    score_document = None
    player_info = None
    players = []
    teams = []

    @staticmethod
    def create():
        Game.score_document = ScoreDocument()
        Game.player_info = Game.score_document.read_range('A2:E30')

        for name, score, games_played, imposter_wins, teammate_wins in Game.player_info:
            Game.players.append(Player(name, score, games_played, imposter_wins, teammate_wins))

    @staticmethod
    def create_team(team_name):
        Game.teams.append(Team(team_name))

    @staticmethod
    def update_players(team_name, player_names):
        for player_name in player_names:
            if not any(player.name == player_name for player in Game.players):
                Game.players.append(Player(player_name, 0, 0, 0, 0))

        if not any(team.name == team_name for team in Game.teams):
            Game.teams.append(Team(team_name))

        team = [team for team in Game.teams if team.name == team_name][0]
        players = [player for player in Game.players if player.name in player_names]
        team.set_players(players)


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
        channel = message.channel
        content = str(message.content)


def main():
    Game.create()


if __name__ == '__main__':
    main()
