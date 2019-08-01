from celery import Celery
from celery.signals import worker_ready

from models.redis import db, LISTENER_TASK_KEY

app = Celery('wechat', include=['wechat.tasks'])
app.config_from_object('wechat.celeryconfig')


# @worker_ready.connect
def at_start(sender, **k):
    with sender.app.connection() as conn:  # noqa
        task_id = sender.app.send_task('wechat.tasks.listener', [sender])
        db.set(LISTENER_TASK_KEY + sender, task_id)


if __name__ == '__main__':
    app.start()
