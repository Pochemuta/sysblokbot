from typing import Callable

from ..app_context import AppContext
from .utils import job_log_start_stop


@job_log_start_stop
def execute(app_context: AppContext, send: Callable[[str], None]):
    # Logic here could include retrieving data from trello/sheets
    # and sending a notification to corresponding user.
    # app_context contain all necessary clients inside.
    print("I am a job and I'm done")
