import os
import subprocess
import logging
from time import sleep
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler


# see https://python-watchdog.readthedocs.io/en/stable/api.html#event-classes
# might as well use `py-mon`: https://pypi.org/project/py-mon/


logging.basicConfig(level=logging.WARNING)


class RestartEventHandler(PatternMatchingEventHandler):
    def __init__(self, command, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.process = None
        self.restart_process()

    def restart_process(self):
        if self.process:
            self.process.terminate()
            self.process.wait()  # Ensure the old process has finished terminating
            sleep(1)  # Allow some time to release the bot API call
        logging.info("Starting bot...")
        self.process = subprocess.Popen(self.command)

    def on_modified(self, event):
        if not self.should_ignore(event.src_path):
            logging.info(
                "File modified: %s, restarting bot...", event.src_path
            )
            self.restart_process()

    def should_ignore(self, path):
        if any(x in path for x in ["venv", ".git", "__pycache__"]):
            return True
        if os.path.basename(path).startswith(".") or os.path.basename(
            path
        ).endswith("~"):
            return True
        if os.path.basename(path).startswith("#") and os.path.basename(
            path
        ).endswith("#"):
            return True
        return False


def main():
    logging.info("Initializing BotReloader...")
    command = ["python", "run_telegram.py"]  # Command to run the bot
    event_handler = RestartEventHandler(
        command, patterns=["*.py"], ignore_directories=True
    )
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()
    try:
        while True:
            sleep(1)  # Prevent tight loop spin
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
