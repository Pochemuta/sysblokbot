import datetime
import logging
from typing import Callable, List

from deepdiff import DeepDiff

from ..app_context import AppContext
from ..scheduler import JobScheduler
from ..trello.trello_client import TrelloClient


logger = logging.getLogger(__name__)


def execute(app_context: AppContext, send: Callable[[str], None] = None):
    """A very special job checking config for recent changes"""
    logger.info('Starting config_updater_job...')
    # get the scheduler instance
    job_scheduler = JobScheduler()
    # if anything at all changed in config
    diff = DeepDiff(
        job_scheduler.config,
        job_scheduler.config_manager.load_config_with_override()
    )
    if diff:
        logger.info(f'Config was changed, diff: {diff}')
        # update config['jobs']
        job_scheduler.reschedule_jobs()
        # update config['telegram']
        tg_config = job_scheduler.config_manager.get_telegram_config()
        job_scheduler.telegram_sender.update_config(tg_config)
        # update admins and managers
        app_context.set_access_rights(tg_config)
        # update config['trello']
        app_context.trello_client.update_config(
            job_scheduler.config_manager.get_trello_config())
        # update config['sheets']
        app_context.sheets_client.update_config(
            job_scheduler.config_manager.get_sheets_config())
    else:
        logger.info('No config changes detected')
    logger.info('Finished config_updater_job')
