import datetime
import logging
from typing import Callable, Iterable, List

import telegram

from ... import consts
from ...app_context import AppContext
from ...trello.trello_objects import TrelloCard
from ...jobs.utils import paragraphs_to_messages, retrieve_username
from .utils import manager_only, reply

TASK_NAME = 'get_tasks_report'

logger = logging.getLogger(__name__)


@manager_only
def get_tasks_report(update: telegram.Update, tg_context: telegram.ext.CallbackContext):
    # set initial dialogue data
    tg_context.chat_data[consts.LAST_ACTIONABLE_COMMAND] = TASK_NAME
    tg_context.chat_data[TASK_NAME] = {
        consts.NEXT_ACTION: consts.PlainTextUserAction.GET_TASKS_REPORT__ENTER_BOARD_URL.value
    }
    reply("Привет! Пришли, пожалуйста, ссылку на доску в Trello.", update)


def generate_report_messages(
        board_id: str,
        list_id: str,
        introduction: str,
        add_labels: bool
) -> List[str]:
    app_context = AppContext()
    paragraphs = []  # list of paragraph strings

    trello_list = app_context.trello_client.get_list(list_id)
    paragraphs.append(
        f'<b>{trello_list.name}</b>'
    )

    list_cards = app_context.trello_client.get_cards([list_id], board_id)
    paragraphs += (_create_paragraphs_from_cards(
        list_cards, introduction, add_labels, app_context
    ))
    return paragraphs_to_messages(paragraphs)


def _create_paragraphs_from_cards(
        cards: Iterable[TrelloCard],
        introduction: str,
        need_label: bool,
        app_context: AppContext
):
    paragraphs = []
    if introduction:
        paragraphs.append(introduction)

    members = _get_members(cards)
    for member in members:
        lines = []
        member_name = _make_member_text(member, app_context.db_client)
        lines.append(member_name)
        member_cards = _get_member_cards(member, cards)
        cards_text = _make_cards_text(
            member_cards, need_label, app_context)
        lines += cards_text
        paragraphs.append('\n'.join(lines))

    # cards without members at the end
    cards_without_members = _get_cards_without_members(cards)
    if cards_without_members:
        lines = ['<b>Разное:</b>']
        cards_without_members_text = _make_cards_text(
            cards_without_members, need_label, app_context)
        lines += cards_without_members_text
        paragraphs.append('\n'.join(lines))
    return paragraphs


def _format_card(card: TrelloCard, need_label: bool) -> str:
    # Name and url always present, labels and deadline optional.
    labels_text = ''
    if need_label and card.labels:
        labels = [f'"{label.name}"' for label in card.labels]
        labels_text = f'({", ".join(labels)})'
    return (
        f'{_make_deadline_text(card) if card.due else ""}'
        f'<a href="{card.url}">{card.name}</a> {labels_text}'
    ).strip()


def _get_members(cards: Iterable[TrelloCard]):
    members = set()
    for card in cards:
        for member in card.members:
            members.add(member)
    return sorted(list(members))


def _get_member_cards(member, cards: Iterable[TrelloCard]):
    member_cards = []
    for card in cards:
        if member in card.members:
            member_cards.append(card)
    return _sort_cards_by_date(member_cards)


def _get_cards_without_members(cards: Iterable[TrelloCard]):
    cards_without_members = []
    for card in cards:
        if not card.members:
            cards_without_members.append(card)
    return _sort_cards_by_date(cards_without_members)


def _make_member_text(member, db_client) -> str:
    return f'👤 <b>{retrieve_username(member, db_client)}</b>:'


def _make_deadline_text(card: TrelloCard) -> str:
    return f'До {card.due.strftime("%d.%m")} — ' if card.due else ''


def _make_cards_text(
        cards: Iterable[TrelloCard],
        need_label: bool,
        app_context: AppContext
) -> List[str]:
    # generates the text of the cards, cards come already sorted by date
    return[_format_card(card, need_label) for card in cards]


def _sort_cards_by_date(cards: Iterable[TrelloCard]) -> Iterable[TrelloCard]:
    return sorted(
        cards,
        key=lambda card: card.due or datetime.datetime(datetime.MINYEAR, 1, 1)
    )