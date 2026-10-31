from config.celery import app
from strategies.services import update_auto_strategies


@app.task
def update_strategies():
    update_auto_strategies()
