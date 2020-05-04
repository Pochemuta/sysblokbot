import datetime
import logging
from typing import Callable, List

from .base_job import BaseJob
from ..app_context import AppContext
from ..consts import TrelloCardColor
from ..trello.trello_client import TrelloClient
from ..sheets.sheets_client import GoogleSheetsClient
from .utils import pretty_send, retrieve_usernames, retrieve_curator_names


logger = logging.getLogger(__name__)


class TrelloBoardStateJob(BaseJob):
    @staticmethod
    def _execute(app_context: AppContext, send: Callable[[str], None]):
        paragraphs = []  # list of paragraph strings
        paragraphs.append('Всем привет! Еженедельная сводка \
о состоянии Trello-доски.\n#доскаживи')

        paragraphs += TrelloBoardStateJob._retrieve_cards_for_paragraph(
            trello_client=app_context.trello_client,
            sheets_client=None,
            title='Не указан автор в карточке',
            list_ids=(
                app_context.lists_config['in_progress'],
                app_context.lists_config['editor'],
                app_context.lists_config['edited_next_week'],
                app_context.lists_config['edited_sometimes'],
                app_context.lists_config['chief_editor'],
                app_context.lists_config['proofreading'],
                app_context.lists_config['done'],
            ),
            filter_func=lambda card: not card.members,
            show_due=False,
            show_members=False,
        )

        paragraphs += TrelloBoardStateJob._retrieve_cards_for_paragraph(
            trello_client=app_context.trello_client,
            sheets_client=app_context.sheets_client,
            title='Не указан срок в карточке',
            list_ids=(app_context.lists_config['in_progress']),
            filter_func=lambda card: not card.due,
            show_due=False
        )

        paragraphs += TrelloBoardStateJob._retrieve_cards_for_paragraph(
            trello_client=app_context.trello_client,
            sheets_client=app_context.sheets_client,
            title='Не указан тег рубрики в карточке',
            list_ids=(
                app_context.lists_config['in_progress'],
                app_context.lists_config['editor'],
                app_context.lists_config['edited_next_week'],
                app_context.lists_config['edited_sometimes'],
                app_context.lists_config['chief_editor'],
                app_context.lists_config['proofreading'],
                app_context.lists_config['done'],
            ),
            filter_func=lambda card: not card.labels,
            show_due=False
        )

        all_cards = app_context.trello_client.get_cards()
        members_with_cards = set()
        for card in all_cards:
            members_with_cards = members_with_cards.union(set(card.members))

        # TODO: probably move to another cmd, @ibulgakov has thoughts on that
        # paragraphs += _retrieve_trello_members_stats(
        #     trello_client=app_context.trello_client,
        #     title='Авторы без карточек',
        #     filter_func=lambda member: member.username not in members_with_cards,
        # )

        paragraphs += TrelloBoardStateJob._retrieve_cards_for_paragraph(
            trello_client=app_context.trello_client,
            sheets_client=app_context.sheets_client,
            title='Пропущен дедлайн',
            list_ids=(app_context.lists_config['in_progress']),
            filter_func=TrelloBoardStateJob._is_deadline_missed,
        )

        pretty_send(paragraphs, send)

    @staticmethod
    def _is_deadline_missed(card) -> bool:
        return card.due is not None and card.due < datetime.datetime.now()

    @staticmethod
    def _retrieve_cards_for_paragraph(
            trello_client: TrelloClient,
            sheets_client: GoogleSheetsClient,
            title: str,
            list_ids: List[str],
            filter_func: Callable,
            show_due=True,
            show_members=True,
    ) -> List[str]:
        '''
        Returns a list of paragraphs that should always go in a single message.
        '''
        logger.info(f'Started counting: "{title}"')
        cards = list(filter(filter_func, trello_client.get_cards(list_ids)))
        parse_failure_counter = 0

        paragraphs = [f'<b>{title}: {len(cards)}</b>']

        for card in cards:
            if not card:
                parse_failure_counter += 1
                continue
            paragraphs.append(
                TrelloBoardStateJob._format_card(
                    card,
                    sheets_client,
                    show_due=show_due,
                    show_members=show_members
                )
            )

        if parse_failure_counter > 0:
            logger.error(f'Unparsed cards encountered: {parse_failure_counter}')
        return paragraphs

    @staticmethod
    def _retrieve_trello_members_stats(
            trello_client: TrelloClient,
            sheets_client: GoogleSheetsClient,
            title: str,
            filter_func: Callable,
    ) -> List[str]:
        '''
        Returns a list of paragraphs that should always go in a single message.
        '''
        logger.info(f'Started counting: "{title}"')
        members = list(filter(filter_func, trello_client.get_members()))
        paragraphs = [f'<b>{title}: {len(members)}</b>']
        if members:
            paragraphs.append('👤 ' + ", ".join(
                retrieve_usernames(sorted(members), sheets_client)
            ))
        return paragraphs

    @staticmethod
    def _format_card(card, sheets_client, show_due=True, show_members=True) -> str:
        # Name and url always present.
        card_text = f'<a href="{card.url}">{card.name}</a>\n'

        # If no labels assigned, don't render them to text.
        if card.labels:
            # We filter BLACK cards as this is an auxiliary label
            label_names = [
                label.name for label in card.labels
                if label.color != TrelloCardColor.BLACK
            ]
            card_text = f'{card_text}📘 {", ".join(label_names)} '

        # Avoiding message overflow, strip explanations in ()
        list_name = card.lst.name + '('
        list_name = list_name[:list_name.find('(')].strip()
        card_text += f'📍 {list_name} '

        if show_due:
            card_text = f'<b>{card.due.strftime("%d.%m")}</b> — {card_text}'
        if show_members and card.members:
            members_text = f'👤 {", ".join(retrieve_usernames(card.members, sheets_client))}'
            # add curators to the list
            # TODO: make it more readable!
            curators = set()
            for member in card.members:
                curator_names = retrieve_curator_names(member, sheets_client)
                if not curator_names:
                    continue
                for curator_text, telegram in curator_names:
                    # curator should not duplicate author or other curator
                    if (
                        curator_text and curator_text not in curators and
                            telegram and telegram not in members_text
                    ):
                        curators.add(curator_text)
            card_text += members_text
            if curators:
                curators_text = ' <b>Куратор:</b> ' + ', '.join(curators)
                card_text += curators_text
        return card_text.strip()