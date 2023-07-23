import datetime
import enum
import os
import zoneinfo
from typing import List, Optional, Union

import discord
import psycopg2
import psycopg2.extras
from discord.ext import commands, tasks

from .UtilityClasses_DiscordBot import base

DATABASE_URL = os.getenv('DATABASE_URL')
ZONE_TOKYO = zoneinfo.ZoneInfo('Asia/Tokyo')
ZONE_UTC = zoneinfo.ZoneInfo('UTC')
DEFAULT_TIMES = [
    datetime.time(hour=0, minute=0, tzinfo=ZONE_TOKYO),
    datetime.time(hour=6, minute=0, tzinfo=ZONE_TOKYO),
    datetime.time(hour=12, minute=0, tzinfo=ZONE_TOKYO),
    datetime.time(hour=18, minute=0, tzinfo=ZONE_TOKYO),
    datetime.time(hour=16, minute=52, tzinfo=ZONE_TOKYO)
]
MAX_HP = 3
HEAL_HP_PER_STREAK = 3
THINKING_FACE = base.Emoji(
    discord=':thinking_face:',
    text='\N{thinking face}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/thinking-face_1f914.png'
)
ROLLING_ON_THE_FLOOR_LAUGHING = base.Emoji(
    discord=':rofl:',
    text='\N{Rolling on the Floor Laughing}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/rolling-on-the-floor-laughing_1f923.png'
)
INNOCENT = base.Emoji(
    discord=':innocent:',
    text='\N{Smiling Face with Halo}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/smiling-face-with-halo_1f607.png'
)
PARTY_POPPER = base.Emoji(
    discord=':tada:',
    text='\N{PARTY POPPER}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/party-popper_1f389.png'
)
PARTY_FACE = base.Emoji(
    discord=':partying_face:',
    text='\N{Face with Party Horn and Party Hat}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/partying-face_1f973.png'
)
CHECK_MARK_BUTTON = base.Emoji(
    discord=':white_check_mark:',
    text='\N{White Heavy Check Mark}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/check-mark-button_2705.png'
)
CROSS_MARK = base.Emoji(
    discord=':x:',
    text='\N{Cross Mark}',
    url='https://em-content.zobj.net/thumbs/240/twitter/322/cross-mark_274c.png'
)


def calc_nearest_datetime(standard: datetime.datetime, _time: datetime.time) -> datetime.datetime:
    diff = datetime.timedelta.max
    nearest_datetime: Optional[datetime.datetime] = None
    for _date in [standard.date() + datetime.timedelta(days=i) for i in range(-1, 2)]:
        if (datetime.datetime.combine(date=_date, time=_time, tzinfo=ZONE_UTC) - standard) < diff:
            nearest_datetime = datetime.datetime.combine(date=_date, time=_time, tzinfo=ZONE_UTC)
            diff = abs(nearest_datetime - standard)
    assert abs(nearest_datetime - standard) < datetime.timedelta(days=1)
    return nearest_datetime


class SettingChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, runner: 'Runner'):
        super().__init__(channel_types=[discord.ChannelType.text])
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.select_channel(values=self.values, interaction=interaction)


class IntervalDaysSelect(discord.ui.Select):
    FORMAT = '{}.interval_days_select'

    def __init__(self, runner: 'Runner'):
        options = [discord.SelectOption(label='毎日', value=self.FORMAT.format(1))] + \
                  [discord.SelectOption(label='{}日ごと'.format(i), value=self.FORMAT.format(i)) for i in range(2, 7)] + \
                  [discord.SelectOption(label='1週間ごと', value=self.FORMAT.format(7))]
        super().__init__(placeholder='送信する間隔', options=options)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        assert len(self.values) == 1
        self.runner.interval = datetime.timedelta(days=int(self.values[0][0]))
        await interaction.response.defer()


class HourSelect(discord.ui.Select):
    FORMAT = '{:0=2}.hour_select'

    def __init__(self, runner: 'Runner'):
        super().__init__(placeholder='時', options=[
            discord.SelectOption(label='{}時'.format(i), value=self.FORMAT.format(i)) for i in range(24)
        ])
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        assert len(self.values) == 1
        self.runner.hour = int(self.values[0][0:2])
        await interaction.response.defer()


class MinuteSelect(discord.ui.Select):
    FORMAT = '{:0=2}.minute_select'

    def __init__(self, runner: 'Runner'):
        super().__init__(placeholder='分', options=[
            discord.SelectOption(label='{}分'.format(i), value=self.FORMAT.format(i)) for i in range(0, 60, 5)
        ])
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        assert len(self.values) == 1
        self.runner.minute = int(self.values[0][0:2])
        await interaction.response.defer()


class NextDaySelect(discord.ui.Select):
    def __init__(self, runner: 'Runner'):
        now = datetime.datetime.now(tz=ZONE_TOKYO)
        super().__init__(placeholder='最初に送信される日', options=[
            discord.SelectOption(label='{}'.format((now + datetime.timedelta(days=i)).date()),
                                 value=(now + datetime.timedelta(days=i)).date().strftime('%Y:%m:%d')) for i in range(7)
        ])
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        assert len(self.values) == 1
        self.runner.next_date = datetime.datetime.strptime(self.values[0], '%Y:%m:%d').date()
        await interaction.response.defer()


class AddButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='追加', style=discord.ButtonStyle.primary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.add(interaction=interaction)


class EditButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='変更', style=discord.ButtonStyle.primary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.edit(interaction=interaction)


class BackButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='戻る', style=discord.ButtonStyle.secondary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.back(interaction=interaction)


class DeleteButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='削除', style=discord.ButtonStyle.danger)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.delete(interaction=interaction)


class MembersButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='報告状況', style=discord.ButtonStyle.primary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.member(interaction=interaction)


class SettingButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='設定', style=discord.ButtonStyle.primary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.setting(interaction=interaction)


class BackMenuButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='戻る', style=discord.ButtonStyle.secondary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.back_menu(interaction=interaction)


class JoinProgress(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='参加する', style=discord.ButtonStyle.primary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.join(interaction)


class LeaveProgress(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='離脱する', style=discord.ButtonStyle.link)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()


class BackMembersButton(discord.ui.Button):
    def __init__(self, runner: 'Runner'):
        super().__init__(label='戻る', style=discord.ButtonStyle.secondary)
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        await self.runner.back_members(interaction=interaction)


class MemberSelect(discord.ui.UserSelect):
    def __init__(self, runner: 'Runner'):
        super().__init__(placeholder='メンバー')
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        self.runner.chosen_member_on_member_status = self.values[0]
        await self.runner.move_member_status(interaction=interaction)


class TextChannelSelectOnMemberStatus(discord.ui.ChannelSelect):
    def __init__(self, runner: 'Runner'):
        super().__init__(placeholder='テキストチャンネル', channel_types=[discord.ChannelType.text])
        self.runner = runner

    async def callback(self, interaction: discord.Interaction):
        self.runner.chosen_channel_on_member_status = self.values[0]
        await self.runner.move_member_status(interaction=interaction)


class ProgressWindow(base.Window):
    class WindowID(enum.IntEnum):
        SETTING = 0
        ADD = 1
        EDIT = 2
        ADDED = 3
        EDITED = 4
        DELETED = 5
        MENU = 6
        MEMBERS = 7
        MEMBER_STATUS = 8
        ERROR_ON_MEMBER_STATUS = 9

    def __init__(self, runner: 'Runner'):
        super().__init__(patterns=10, embed_patterns=[
            {'title': '進捗報告チャンネル　設定',
             'description': '進捗報告用のチャンネルを設定できます。進捗報告がないメンバーには催促のメンションが飛びます。'},
            {'title': '追加', 'description': '時間を指定して追加できます。'},
            {'title': '変更', 'description': '時間を変更できます。'},
            {'title': '追加 完了'},
            {'title': '変更 完了'},
            {'title': '削除 完了'},
            {'title': '進捗報告 監視',
             'description': '設定したチャンネルに進捗報告があるか監視します。指定した期間内に報告がない場合はメンションが飛びます。また一定回数報告がない場合はこのサーバーからKickされます。'},
            {'title': '進捗報告　状況', 'description': 'メンバーの進捗報告状況が確認できます。'},
            {'title': 'member name'},
            {'title': 'エラー', 'color': discord.Colour.orange().value},
            {'title': '{0}は進捗報告のメンバーに登録されていません。', 'color': discord.Colour.orange().value}
        ], view_patterns=[
            [SettingChannelSelect(runner=runner), BackMenuButton(runner=runner)],
            [IntervalDaysSelect(runner=runner), HourSelect(runner=runner), MinuteSelect(runner=runner),
             NextDaySelect(runner=runner), AddButton(runner=runner), BackButton(runner=runner)],
            [IntervalDaysSelect(runner=runner), HourSelect(runner=runner), MinuteSelect(runner=runner),
             NextDaySelect(runner=runner), EditButton(runner=runner), BackButton(runner=runner),
             DeleteButton(runner=runner)],
            [BackButton(runner=runner)], [BackButton(runner=runner)], [BackButton(runner=runner)],
            [MembersButton(runner=runner), SettingButton(runner=runner)],
            [TextChannelSelectOnMemberStatus(runner=runner), MemberSelect(runner=runner),
             BackMenuButton(runner=runner)],
            [LeaveProgress(runner=runner), BackMembersButton(runner=runner)],
            [BackMembersButton(runner=runner)],
            [JoinProgress(runner=runner), BackMembersButton(runner=runner)]
        ])


class Runner(base.Runner):
    def __init__(self, command: 'Progress', channel: discord.TextChannel, database_connector):
        super().__init__(channel=channel)
        self.command = command
        self.progress_window = ProgressWindow(runner=self)
        self.database_connector = database_connector
        self.chosen_channel: Optional[discord.TextChannel] = None
        self.prev_interval: Optional[datetime.timedelta] = None
        self.interval: Optional[datetime.timedelta] = None
        self.prev_time: Optional[datetime.time] = None
        self.hour: Optional[int] = None
        self.minute: Optional[int] = None
        self.prev_next_date: Optional[datetime.date] = None
        self.next_date: Optional[datetime.date] = None
        self.chosen_channel_on_member_status: Union[
            discord.app_commands.AppCommandChannel, discord.app_commands.AppCommandThread, None] = None
        self.chosen_member_on_member_status: Union[discord.Member, discord.User, None] = None

    async def run(self):
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.MENU)
        await self.progress_window.send(sender=self.channel)

    async def select_channel(self, values: List[discord.app_commands.AppCommandChannel],
                             interaction: discord.Interaction):
        assert len(values) == 1
        self.chosen_channel = values[0].resolve()
        with self.database_connector.cursor() as cur:
            cur.execute('SELECT interval, time, timestamp FROM progress WHERE channel_id = %s',
                        (self.chosen_channel.id,))
            results = cur.fetchall()
            self.database_connector.commit()
        if len(results) == 0:
            self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ADD)
            self.progress_window.embed_dict['title'] = '追加 #{}'.format(self.chosen_channel.name)
        elif len(results) == 1:
            self.prev_interval = results[0][0]
            self.prev_time = datetime.datetime.combine(date=datetime.date.today(), time=results[0][1],
                                                       tzinfo=ZONE_UTC).astimezone(tz=ZONE_TOKYO).time()
            self.prev_next_date = results[0][2].astimezone(tz=ZONE_TOKYO).date()
            self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.EDIT)
            self.progress_window.embed_dict['title'] = '変更 #{}'.format(self.chosen_channel.name)
            self.progress_window.embed_dict['fields'] = [
                {'name': '送信する間隔', 'value': '{}日ごと'.format(self.prev_interval.days)},
                {'name': '送信する時刻', 'value': '{0}時{1}分'.format(self.prev_time.hour, self.prev_time.minute)},
                {'name': '次に送信される日付', 'value': str(self.prev_next_date)}
            ]
        else:
            raise ValueError
        await self.progress_window.response_edit(interaction=interaction)

    async def add(self, interaction: discord.Interaction):
        if self.interval is None or self.hour is None or self.minute is None or self.next_date is None:
            self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ADD)
            self.progress_window.embed_dict['color'] = discord.Colour.orange().value
            self.progress_window.embed_dict['fields'] = [{'name': 'エラー', 'value': '要素をすべて選択してください。'}]
        else:
            now = datetime.datetime.now(tz=ZONE_TOKYO)
            new_time = datetime.time(hour=self.hour, minute=self.minute, tzinfo=ZONE_TOKYO)
            next_datetime = datetime.datetime.combine(date=self.next_date, time=new_time)
            new_time_utc = next_datetime.astimezone(tz=ZONE_UTC).time()
            if next_datetime < now:
                self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ADD)
                self.progress_window.embed_dict['color'] = discord.Colour.orange().value
                self.progress_window.embed_dict['fields'] = [
                    {'name': 'エラー', 'value': '次回の時刻は現在以降の時刻を設定してください。'}]
            else:
                with self.database_connector.cursor() as cur:
                    cur.execute('SELECT channel_id FROM progress WHERE channel_id = %s', (self.chosen_channel.id,))
                    results = cur.fetchall()
                    if len(results) == 0:
                        cur.execute(
                            'INSERT INTO progress (channel_id, interval, time, timestamp, prev_timestamp,'
                            ' prev_prev_timestamp) VALUES (%s, %s, %s, %s, %s, %s)',
                            (self.chosen_channel.id, self.interval, new_time_utc, next_datetime,
                             next_datetime - self.interval, next_datetime - self.interval * 2)
                        )
                        self.database_connector.commit()
                    else:
                        cur.execute(
                            'UPDATE progress SET interval = %s, time = %s, timestamp = %s WHERE channel_id = %s',
                            (self.interval, new_time_utc, next_datetime, self.chosen_channel.id)
                        )
                        self.database_connector.commit()
                self.command.change_printer_interval()
                self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ADDED)
                self.progress_window.embed_dict['fields'] = [
                    {'name': '送信する間隔', 'value': '{}日ごと'.format(self.interval.days)},
                    {'name': '送信する時刻', 'value': '{0}時{1}分'.format(self.hour, self.minute)},
                    {'name': '次に送信される日付', 'value': str(self.next_date)}
                ]
        await self.progress_window.response_edit(interaction=interaction)

    async def edit(self, interaction: discord.Interaction):
        if self.interval is None or self.hour is None or self.minute is None or self.next_date is None:
            self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.EDIT)
            self.progress_window.embed_dict['color'] = 0x8b0000
            self.progress_window.embed_dict['fields'] = [{'name': 'エラー', 'value': '要素をすべて選択してください。'}]
        else:
            now = datetime.datetime.now(tz=ZONE_TOKYO)
            new_time = datetime.time(hour=self.hour, minute=self.minute, tzinfo=ZONE_TOKYO)
            next_datetime = datetime.datetime.combine(date=self.next_date, time=new_time)
            new_time_utc = next_datetime.astimezone(tz=ZONE_UTC).time()
            if next_datetime < now:
                self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.EDIT)
                self.progress_window.embed_dict['color'] = 0x8b0000
                self.progress_window.embed_dict['fields'] = [
                    {'name': 'エラー', 'value': '次回の時刻は現在以降の時刻を設定してください。'}]
            else:
                with self.database_connector.cursor() as cur:
                    cur.execute('SELECT channel_id FROM progress WHERE channel_id = %s', (self.chosen_channel.id,))
                    results = cur.fetchall()
                    if len(results) == 0:
                        cur.execute(
                            'INSERT INTO progress (channel_id, interval, time, timestamp, prev_timestamp,'
                            ' prev_prev_timestamp) VALUES (%s, %s, %s, %s, %s, %s)',
                            (self.chosen_channel.id, self.interval, new_time_utc, next_datetime,
                             next_datetime - self.interval, next_datetime - self.interval * 2)
                        )
                        self.database_connector.commit()
                    else:
                        cur.execute(
                            'UPDATE progress SET interval = %s, time = %s, timestamp = %s WHERE channel_id = %s',
                            (self.interval, new_time_utc, next_datetime, self.chosen_channel.id)
                        )
                        self.database_connector.commit()
                self.command.change_printer_interval()
                self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.EDITED)
                self.progress_window.embed_dict['fields'] = [
                    {'name': '送信する間隔', 'value': '{}日ごと'.format(self.interval.days)},
                    {'name': '送信する時刻', 'value': '{0}時{1}分'.format(self.hour, self.minute)},
                    {'name': '次に送信される日付', 'value': str(self.next_date)}
                ]
        await self.progress_window.response_edit(interaction=interaction)

    async def back(self, interaction: discord.Interaction):
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.SETTING)
        await self.progress_window.response_edit(interaction=interaction)

    async def delete(self, interaction: discord.Interaction):
        with self.database_connector.cursor() as cur:
            cur.execute('DELETE FROM progress WHERE channel_id = %s', (self.chosen_channel.id,))
            self.database_connector.commit()
        self.command.change_printer_interval()
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.DELETED)
        await self.progress_window.response_edit(interaction=interaction)

    async def member(self, interaction: discord.Interaction):
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.MEMBERS)
        await self.progress_window.response_edit(interaction=interaction)

    async def setting(self, interaction: discord.Interaction):
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.SETTING)
        await self.progress_window.response_edit(interaction=interaction)

    async def back_menu(self, interaction: discord.Interaction):
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.MENU)
        await self.progress_window.response_edit(interaction=interaction)

    async def move_member_status(self, interaction: discord.Interaction):
        if self.chosen_member_on_member_status is None or self.chosen_channel_on_member_status is None:
            await interaction.response.defer()
        else:
            try:
                channel = await self.chosen_channel_on_member_status.fetch()
            except discord.NotFound:
                self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ERROR_ON_MEMBER_STATUS)
                self.progress_window.embed_dict['title'] = '# {0}はこのサーバーに存在しません。'.format(
                    self.chosen_channel_on_member_status.name)
                await self.progress_window.response_edit(interaction=interaction)
            else:
                with self.database_connector.cursor() as cur:
                    cur.execute(
                        'SELECT * FROM progress WHERE channel_id = %s', (channel.id,)
                    )
                    results = cur.fetchall()
                if len(results) == 0:
                    self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ERROR_ON_MEMBER_STATUS)
                    self.progress_window.embed_dict['title'] = '# {0}は進捗報告チャンネルとして登録されていません。'.format(
                        channel.name)
                    await self.progress_window.response_edit(interaction=interaction)
                elif len(results) == 1:
                    if self.chosen_member_on_member_status in channel.members:
                        with self.database_connector.cursor() as cur:
                            cur.execute(
                                'SELECT score, total, streak, escape, denied FROM progress_members'
                                ' WHERE channel_id = %s AND user_id = %s',
                                (channel.id, self.chosen_member_on_member_status.id)
                            )
                            results = cur.fetchall()
                            self.database_connector.commit()
                        if len(results) == 0:
                            self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ERROR_ON_MEMBER_STATUS)
                            self.progress_window.embed_dict['title'] = '{0}さんは# {1}のprogressに参加していません'.format(
                                self.chosen_member_on_member_status.name, channel.name)
                            await self.progress_window.response_edit(interaction=interaction)
                        elif len(results) == 1:
                            score, total, streak, escape, denied = results[0]
                            self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.MEMBER_STATUS)
                            self.progress_window.embed_dict['title'] = '*{}*'.format(
                                self.chosen_member_on_member_status.name)
                            self.progress_window.embed_dict['thumbnail'] = {
                                'url': self.chosen_member_on_member_status.display_avatar.url}
                            self.progress_window.embed_dict['fields'] = [
                                {'name': '今月のスコア', 'value': '{}'.format(score)},
                                {'name': '報告回数', 'value': '{}回'.format(total)},
                                {'name': '報告連続日数', 'value': '{}日'.format(max(streak, 0))},
                                {'name': '報告忘れ回数', 'value': '{}回'.format(escape)},
                                {'name': '却下された回数', 'value': '{}回'.format(denied)},
                                {'name': '報告無し連続日数', 'value': '{}日'.format(max(-streak, 0))}
                            ]
                            await self.progress_window.response_edit(interaction=interaction)
                        else:
                            raise RuntimeError
                    else:
                        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ERROR_ON_MEMBER_STATUS)
                        self.progress_window.embed_dict['title'] = '{0}は# {1}に参加していません。'.format(
                            self.chosen_member_on_member_status.name, channel.name)
                        await self.progress_window.response_edit(interaction=interaction)
                else:
                    raise RuntimeError
                self.chosen_member_on_member_status = None
                self.chosen_channel_on_member_status = None

    async def back_members(self, interaction: discord.Interaction):
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.MEMBERS)
        await self.progress_window.response_edit(interaction=interaction)

    async def join(self, interaction: discord.Interaction):
        with self.database_connector.cursor() as cur:
            cur.execute(
                'INSERT INTO progress_members (channel_id, user_id, total, streak, escape, denied, score)'
                ' VALUES (%s, %s, 0, 0, 0, 0, 0)', (
                    self.chosen_channel_on_member_status.id, self.chosen_member_on_member_status
                )
            )
            self.database_connector.commit()
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.MEMBER_STATUS)
        await self.progress_window.response_edit(interaction=interaction)

    async def leave(self, interaction: discord.Interaction):
        with self.database_connector.cursor() as cur:
            cur.execute(
                'DELETE FROM progress_members WHERE channel_id = %s AND user_id = %s', (
                    self.chosen_channel_on_member_status.id, self.chosen_member_on_member_status.id
                )
            )
            self.database_connector.commit()
        self.progress_window.set_pattern(pattern_id=ProgressWindow.WindowID.ERROR_ON_MEMBER_STATUS)
        await self.progress_window.response_edit(interaction=interaction)


class Progress(base.Command):
    def __init__(self, bot: discord.ext.commands.Bot):
        super().__init__(bot=bot)
        self.tally_progress_periodically.start()
        print(self.tally_progress_periodically.next_iteration)
        self.parser.add_argument('comment')

        # Databaseの初期化
        self.database_connector = psycopg2.connect(DATABASE_URL)
        with self.database_connector.cursor() as cur:
            cur.execute(
                'CREATE TABLE IF NOT EXISTS progress (channel_id BIGINT, interval INTERVAL, time TIME,'
                ' timestamp TIMESTAMPTZ, prev_timestamp TIMESTAMPTZ, prev_prev_timestamp TIMESTAMPTZ,'
                ' PRIMARY KEY (channel_id))')
            self.database_connector.commit()
        self.change_printer_interval()

        with self.database_connector.cursor() as cur:
            cur.execute(
                'CREATE TABLE IF NOT EXISTS progress_members (channel_id BIGINT, user_id BIGINT, score INTEGER,'
                ' total INTEGER, streak INTEGER, escape INTEGER, denied INTEGER, PRIMARY KEY (channel_id, user_id))'
            )
            self.database_connector.commit()

        with self.database_connector.cursor() as cur:
            cur.execute(
                'CREATE TABLE IF NOT EXISTS progress_reports (channel_id BIGINT, user_id BIGINT, message_id BIGINT,'
                ' timestamp TIMESTAMPTZ, PRIMARY KEY (channel_id, user_id, message_id))'
            )
            self.database_connector.commit()

    def change_printer_interval(self):
        print('changed printer interval.')
        with self.database_connector.cursor() as cur:
            cur.execute('SELECT time FROM progress')
            results = cur.fetchall()
        new_time = [datetime.datetime.combine(date=datetime.datetime.now(tz=ZONE_TOKYO), time=_time).astimezone(
            tz=ZONE_UTC).timetz() for _time in DEFAULT_TIMES] + [_time.replace(tzinfo=ZONE_UTC) for _time, in results]
        for _time in new_time:
            print(_time.tzinfo)
            print(_time)
        self.tally_progress_periodically.change_interval(time=new_time)
        self.tally_progress_periodically.restart()
        print(self.tally_progress_periodically.time)

    @commands.command()
    async def progress(self, ctx: commands.Context, *args):
        print('progress was called.')
        print('printer next iteration is {}'.format(self.tally_progress_periodically.next_iteration))
        print(self.tally_progress_periodically.time)
        try:
            namespace = self.parser.parse_args(args=args)
        except base.commandparser.InputInsufficientRequiredArgumentError:
            self.runners.append(Runner(command=self, channel=ctx.channel, database_connector=self.database_connector))
            await self.runners[len(self.runners) - 1].run()
        else:
            embed = discord.Embed(
                title=namespace.comment, timestamp=datetime.datetime.now(tz=ZONE_TOKYO),
                colour=discord.Colour.light_gray()
            )
            embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            embed.set_footer(text='進捗報告')
            message = await ctx.send(embed=embed)
            await message.add_reaction('\N{thinking face}')
            with self.database_connector.cursor() as cur:
                cur.execute(
                    'INSERT INTO progress_reports (channel_id, message_id, user_id, timestamp) VALUES (%s, %s, %s, %s)',
                    (ctx.channel.id, message.id, ctx.author.id, message.created_at)
                )
                self.database_connector.commit()

    # 進捗を集計する。設定した時刻に呼ばれる。
    @tasks.loop(time=DEFAULT_TIMES)
    async def tally_progress_periodically(self):
        print('tally progress.')
        now = datetime.datetime.now(tz=ZONE_UTC)
        with self.database_connector.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                'SELECT channel_id, interval, time, timestamp, prev_timestamp, prev_prev_timestamp FROM progress')
            results = cur.fetchall()
            self.database_connector.commit()

        # 登録されているprogressごとに集計する。
        for channel_id, interval, _time, timestamp, prev_timestamp, prev_prev_timestamp in results:
            timestamp = timestamp.astimezone(tz=ZONE_UTC)
            prev_timestamp = prev_timestamp.astimezone(tz=ZONE_UTC)
            prev_prev_timestamp = prev_prev_timestamp.astimezone(tz=ZONE_UTC)
            print('現在:{}'.format(now))
            print('予定時刻:{}'.format(timestamp))
            print('前回時刻:{}'.format(prev_timestamp))
            print('前々回時刻{}'.format(prev_prev_timestamp))
            if now + datetime.timedelta(minutes=1) < timestamp:
                continue
            channel = self.bot.get_channel(channel_id)
            # 登録されているchannelが存在しなかったらそのprogressを削除する。
            if channel is None:
                with self.database_connector.cursor() as cur:
                    cur.execute(
                        'DELETE FROM progress WHERE channel_id = %s', (channel_id,)
                    )
                    self.database_connector.commit()
                continue

            # progressに登録されているメンバーを取得
            with self.database_connector.cursor() as cur:
                cur.execute(
                    'SELECT user_id FROM progress_members WHERE channel_id = %s',
                    (channel_id,)
                )
                user_ids = cur.fetchall()
                self.database_connector.commit()

            print(user_ids)
            print('Channel name: {}'.format(channel.name))
            # progressに参加しているかつchannelに所属しているmemberを取得
            members = [member for member in channel.members if
                       member.id in [user_id[0] for user_id in user_ids] and member.id is not self.bot.user.id]
            print('Member name: {}'.format([member.name for member in members]))

            embeds = []
            # 前回のreportの検証
            approved: dict[int, int] = {member.id: 0 for member in members}
            denied: dict[int, int] = {member.id: 0 for member in members}
            # 前回の期間内の進捗報告を取得
            with self.database_connector.cursor() as cur:
                cur.execute(
                    'SELECT message_id, user_id FROM progress_reports'
                    ' WHERE channel_id = %s AND %s <= timestamp AND timestamp < %s',
                    (channel_id, prev_prev_timestamp, prev_timestamp)
                )
                results = cur.fetchall()
                self.database_connector.commit()
            # 取得した進捗報告を集計
            for message_id, user_id in results:
                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    continue
                else:
                    if user_id in [member.id for member in members]:
                        reactions = [
                            reaction for reaction in message.reactions if type(
                                reaction.emoji) == str and reaction.emoji == THINKING_FACE.text]
                        if len(reactions) == 1:
                            if reactions[0].count < len(members) / 2:
                                approved[user_id] += 1
                                embed_dict = message.embeds[0].to_dict()
                                embed_dict['thumbnail'] = {'url': CHECK_MARK_BUTTON.url}
                                embed_dict['color'] = discord.Colour.green().value
                                await message.edit(embed=discord.Embed.from_dict(embed_dict))
                            else:
                                denied[user_id] += 1
                                embed_dict = message.embeds[0].to_dict()
                                embed_dict['thumbnail'] = {'url': CROSS_MARK.url}
                                embed_dict['color'] = discord.Colour.red().value
                                await message.edit(embed=discord.Embed.from_dict(embed_dict))
                        else:
                            raise ValueError
            with self.database_connector.cursor() as cur:
                for member in members:
                    cur.execute(
                        'SELECT streak FROM progress_members WHERE channel_id = %s AND user_id = %s',
                        (channel_id, member.id)
                    )
                    result = cur.fetchone()
                    if result is None:
                        continue
                    else:
                        streak, = result
                    if approved[member.id] > 0:
                        # 承認された進捗報告があったとき
                        cur.execute(
                            'UPDATE progress_members SET score = score + %s, total = total + %s, streak = %s,'
                            ' denied = denied + %s WHERE channel_id = %s AND user_id = %s',
                            (
                                approved[member.id] * 100 - denied[member.id] * 50 + streak, approved[member.id],
                                max(streak + 1, 1), denied[member.id], channel_id, member.id
                            )
                        )
                        self.database_connector.commit()
                    else:
                        if denied[member.id] > 0:
                            # 承認された報告がなく、かつ却下された進捗報告があったとき
                            cur.execute(
                                'UPDATE progress_members SET score = score + %s, streak = %s, denied = denied + %s'
                                ' WHERE channel_id = %s AND user_id = %s',
                                (-denied[member.id] * 50 + streak, min(streak - 1, -1), denied[member.id], channel_id,
                                 member.id)
                            )
                            self.database_connector.commit()
                        else:
                            # 進捗報告がなかったとき 前日の時点で集計済み
                            self.database_connector.commit()
            print('approved')
            print(approved)
            print('denied')
            print(denied)
            if 0 < max(approved.values()):
                names = ''
                for member in members:
                    if approved[member.id] > 0:
                        if names == '':
                            names = member.name
                        else:
                            names = '{0}, {1}'.format(names, member.name)
                embed = discord.Embed(
                    title='進捗報告承認!!', description=names, colour=discord.Colour.green()
                )
                embed.set_thumbnail(url=PARTY_POPPER.url)
                embed.set_footer(text='{0}から{1}まで'.format(
                    prev_prev_timestamp.astimezone(tz=ZONE_TOKYO).strftime('%年%m月%d日%H時%M分'),
                    prev_timestamp.astimezone(tz=ZONE_TOKYO).strftime('%年%m月%d日%H時%M分')
                ))
                embeds.append(embed)

            if 0 < max(denied.values()):
                names = ''
                for member in members:
                    if denied[member.id] > 0:
                        if names == '':
                            names = member.name
                        else:
                            names = '{0}, {1}'.format(names, member.name)
                embed = discord.Embed(
                    title='進捗報告却下', description=names, colour=discord.Colour.red()
                )
                embed.set_thumbnail(url=INNOCENT.url)
                embed.set_footer(text='{0}から{1}まで'.format(
                    prev_prev_timestamp.astimezone(tz=ZONE_TOKYO).strftime('%年%m月%d日%H時%M分'),
                    prev_timestamp.astimezone(tz=ZONE_TOKYO).strftime('%年%m月%d日%H時%M分')
                ))
                embeds.append(embed)

            # 今回のreportの検証
            reports: dict[int, int] = {member.id: 0 for member in members}
            with self.database_connector.cursor() as cur:
                cur.execute(
                    'SELECT message_id, user_id FROM progress_reports '
                    'WHERE channel_id = %s AND %s <= timestamp AND timestamp < %s',
                    (channel_id, prev_timestamp, timestamp)
                )
                results = cur.fetchall()
                self.database_connector.commit()
            print(len(results))
            print(channel_id)
            for message_id, user_id in results:
                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    print('Not Found')
                    continue
                else:
                    if user_id in [member.id for member in members]:
                        reports[user_id] += 1

            next_timestamp = calc_nearest_datetime(now, _time.replace(tzinfo=ZONE_UTC)) + interval

            # 進捗催促
            print(reports)
            if 0 in reports.values():
                mentions = ''
                for member in [member for member in members if reports[member.id] == 0]:
                    mentions = '{0} {1}'.format(mentions, member.name)
                embed = discord.Embed(title='進捗どうですか??', description=mentions, colour=discord.Colour.orange())
                embed.set_footer(
                    text='次回は{}です。'.format(next_timestamp.astimezone(tz=ZONE_TOKYO).strftime('%Y年%m月%d日%H時%M分')))
                embed.set_thumbnail(url=THINKING_FACE.url)
                embeds.append(embed)
            else:
                embed = discord.Embed(title='全員報告済み!!', colour=discord.Colour.blue())
                embed.set_thumbnail(url=PARTY_FACE.url)
                embeds.append(embed)

            # スコア　ランキング
            with self.database_connector.cursor() as cur:
                cur.execute(
                    'SELECT user_id, score FROM progress_members WHERE channel_id = %s and user_id = ANY(%s) '
                    'ORDER BY score DESC LIMIT 3', (channel_id, [member.id for member in members])
                )
                results = cur.fetchall()
                self.database_connector.commit()
            embed = discord.Embed(title='現在のスコア　ランキング')
            for i in range(len(results)):
                embed.add_field(name='{}位: {}'.format(i + 1, channel.guild.get_member(results[i][0]).name),
                                value='{}'.format(results[i][1]))
            embeds.append(embed)

            await channel.send(embeds=embeds)

            # 古いreportの削除
            # channelの情報の更新
            with self.database_connector.cursor() as cur:
                cur.execute(
                    'DELETE FROM progress_reports WHERE timestamp < %s', (prev_prev_timestamp,)
                )
                cur.execute(
                    'UPDATE progress SET timestamp = %s, prev_timestamp = %s, prev_prev_timestamp = %s '
                    'WHERE channel_id = %s',
                    (next_timestamp, timestamp, prev_timestamp, channel_id)
                )
                self.database_connector.commit()


async def setup(bot: discord.ext.commands.Bot):
    await bot.add_cog(Progress(bot=bot))
