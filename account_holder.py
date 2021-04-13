import subprocess
import threading
from datetime import datetime, timedelta
import time
import unicodedata
import re
import configparser

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

config = configparser.ConfigParser()
config.read('config.ini')
token = config['DEFAULT']['token']
message_prefix = config['DEFAULT']['message_prefix']
message_deleting_delay = int(config['DEFAULT']['message_deleting_delay'])

lastread = datetime.now()
write_wait = 0.3
output_cache = []

def remove_control_characters(s):
    s1 = ""
    ansi_escape = re.compile(r'''
        \x1B  # ESC
        (?:   # 7-bit C1 Fe (except CSI)
            [@-Z\\-_]
        |     # or [ for CSI, followed by a control sequence
            \[
            [0-?]*  # Parameter bytes
            [ -/]*  # Intermediate bytes
            [@-~]   # Final byte
        )
    ''', re.VERBOSE)
    s1 = ansi_escape.sub('', s)
    cr_pos = s1.rfind('\x0D')
    if cr_pos != -1:
        s1 = s1[cr_pos:]
    return "".join(ch for ch in s1 if unicodedata.category(ch)[0]!="C")

def read_thread_func(print_lines):
    while True:
        global lastread
        exit_code = proc.poll()
        if exit_code != None:
            break
        line = proc.stdout.readline()
        output_cache.append(line)
        if print_lines:
            print(line.decode('utf-8'), end='')
        lastread = datetime.now()
        if line.strip() == b"halt":
            break

def wait_for(delta):
    global lastread
    lastread = datetime.now()
    while (datetime.now() - lastread) / timedelta(seconds=1) < delta:
        time.sleep(0.1)

def tg_write(msg, delta = write_wait):
    proc.stdin.write((msg + "\n").encode("utf-8"))
    proc.stdin.flush()
    wait_for(delta)

def get_cache_str():
    result = ""
    for l in output_cache:
        line = remove_control_characters(l.decode("utf-8").strip())
        if not line.startswith(">"):
            result += line + '\n'
    return result

def read_phone_code():
    global output_cache
    tg_write("dialog_list", 3.0)
    output_cache = []
    tg_write("history Telegram 1")
    return get_cache_str()

def read_self():
    global output_cache
    output_cache = []
    tg_write("get_self")
    return get_cache_str()

def delete_message_with_delay(msg, delay = message_deleting_delay):
    def delete_message():
        time.sleep(delay)
        msg.delete()
    deleting_thread = threading.Thread(target=delete_message, args=())
    deleting_thread.start()

def send_auto_delete_text(msg, text):
    delete_message_with_delay(msg.reply_text(text))

def do_tg(profile, func):
    global proc
    proc = subprocess.Popen(["telegram-cli", "-p", profile], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    read_thread = threading.Thread(target=read_thread_func, args=(False,))
    read_thread.start()
    time.sleep(0.1)
    wait_for(write_wait)
    result = func()
    tg_write("quit")
    read_thread.join()
    proc.terminate()
    return result

def check_format(txt):
    return len(txt.split()) == 2 and txt.split()[0] == message_prefix

def find_code_handler(update: Update, context: CallbackContext) -> None:
    txt = update.message.text
    if not check_format(txt):
        update.message.reply_text(txt)
    else:
        try:
            result = do_tg(txt.split()[1], lambda: read_phone_code() + '\n\r' + read_self())
        except:
            result = "Invalid profile"
        send_auto_delete_text(update.message, result)
        delete_message_with_delay(update.message)

def start(update: Update, context: CallbackContext) -> None:
    delete_message_with_delay(update.message)

def main():
    updater = Updater(token, use_context=True)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, find_code_handler))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()