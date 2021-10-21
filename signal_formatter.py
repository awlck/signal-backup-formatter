import datetime
import pathlib
import sqlite3
import sys
import typing

from dataclasses import dataclass
from shutil import copy2

MIME_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'application/pdf': 'pdf',
    'video/mp4': 'mp4',
    'video/webm': 'webm',
    'audio/aac': 'aac'
}


def prepare_output(target: pathlib.Path):
    target.mkdir(parents=True, exist_ok=True)
    with open(target/'style.css', 'w') as f:
        f.write("""
/* Heavily inspired by: https://codepen.io/samuelkraft/pen/Farhl */
:root {
  --send-bg: #0B93F6;
  --send-color: white;
  --receive-bg: #E5E5EA;
  --receive-text: black;
  --page-background: white;
  --info-text: #777;
}

body {
  font-family: "Helvetica Neue", Helvetica, sans-serif;
  font-size: 20px;
  font-weight: normal;
  max-width: 500px;
  margin: 50px auto;
  display: flex;
  flex-direction: column;
  background-color: var(--page-background);
}

div {
  max-width: 305px;
  word-wrap: break-word;
  margin-bottom: 12px;
  line-height: 24px;
  position: relative;
  padding: 10px 20px;
  border-radius: 25px;
}

div::before, div::after {
  content: "";
  position: absolute;
  bottom: 0;
  height: 25px;
}

.send {
  color: var(--send-color); 
  background: var(--send-bg);
  align-self: flex-end;
}
.send::before {
  right: -7px;
  width: 20px;
  background-color: var(--send-bg);
  border-bottom-left-radius: 16px 14px;
}
.send::after {
  right: -26px;
  width: 26px;
  background-color: var(--page-background);
  border-bottom-left-radius: 10px;
}

.receive {
  background: var(--receive-bg);
  color: black;
  align-self: flex-start;
}
.receive::before {
  left: -7px;
  width: 20px;
  background-color: var(--receive-bg);
  border-bottom-right-radius: 16px 14px;
}
.receive::after {
  left: -26px;
  width: 26px;
  background-color: var(--page-background);
  border-bottom-right-radius: 10px;
}

.sender {
  font-size: small;
  margin-top: 0px;
  margin-bottom: 0px;
  padding-top: 2px;
  padding-bottom: 1px;
  padding-left: 10px;
  bottom: 0px;
  color: var(--info-text);
  font-weight: bold;
}
  
p.sent {
  font-size: x-small;
  line-height: 0px;
  font-weight: bold;
}
.receive>p.sent {
  text-align: right;
  margin-right: -5px;
  color: #555555;
}
.send>p.sent {
  margin-left: -5px;
  color: #eaeaea;
}

.date {
  display: block;
  margin-left: auto;
  margin-right: auto;
  margin-bottom: 0px;
  padding-bottom: 0px;
  font-size: small;
  font-weight: bold;
  color: var(--info-text);
}
""")


def write_prelude(target: typing.TextIO, name: str):
    target.write(f"""
<!DOCTYPE html>
<html>
<head>
<title>{name}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<h1>{name}</h1>
""")


def write_footer(target: typing.TextIO):
    target.write("""
<a href="index.html">Return</a>
</body>
</html>
""")


@dataclass
class Message:
    id: int
    date: int
    sender: int
    body: str

    def to_html(self, senders=None):
        if self.body is not None:
            result = ""
            if senders is not None and self.sender is not None:
                result = f"""<p class="sender">{senders[self.sender]}</p>"""
            result += f"""<div class="{'send' if self.sender is None else 'receive'}">{self.body.replace(chr(10), '<br/>')}<p class="sent">{datetime.datetime.fromtimestamp(self.date/1000).strftime("%H:%M")}</p></div>"""
            return result


class SMS(Message):
    pass


class MMS(Message):
    def mms_to_html(self, src, target, cursor, senders=None):
        content = ""
        cursor.execute('select _id as id, ct, file_name, unique_id from part where mid = ?', (self.id,))
        atts = cursor.fetchall()
        for att in atts:
            src_file = src/f'Attachment_{att[0]}_{att[3]}.bin'
            if att[1] in MIME_EXT:
                target_file = target/(f'{att[3]}_{att[2]}' if att[2] is not None else f'Attachment{att[0]}.{MIME_EXT[att[1]]}')
            else:
                target_file = target / src_file.name
            copy2(src_file, target_file)
            if att[1] in ('image/png', 'image/jpeg', 'image/webp', 'image/gif'):
                content += f'<img src="{target_file.name}" width="100%">'
            elif att[1] == 'audio/aac' and att[2] is None:
                content += f'Voice message:<audio controls src="{target_file.name}"></audio>'
            elif att[1] == 'video/mp4':
                content += f'<video controls width="100%"><source src="{target_file.name}" type="video/mp4"></video>'
            elif att[1] == 'application/pdf':
                content += f'<a href="{target_file.name}">PDF Document</a>'
            else:
                content += f'<a href="{target_file.name}">Unknown attachment</a>'
        if self.body:
            content += self.body.replace('\n', '<br>')
        if content:
            if senders is not None and self.sender is not None:
                sendinfo = f'<p class="sender">{senders[self.sender]}</p>'
            else:
                sendinfo = ''
            return f"""{sendinfo}<div class="{'send' if self.sender is None else 'receive'}">{content}<p class="sent">{datetime.datetime.fromtimestamp(self.date/1000).strftime("%H:%M")}</p></div>"""
        return ""


def format_indiv_thread(cursor: sqlite3.Cursor, thread, src: pathlib.Path, target: pathlib.Path) -> bool:
    """
    :param cursor: The connection cursor
    :param thread: The thread to format
    :param src: The source folder.
    :param target: The output folder in which to write the HTML file, if necessary
    :return: True if any messages were found and written.
    """
    msgs = load_messages(cursor, thread)
    if not msgs:
        # no results, this thread is empty
        return False
    last_date_written = datetime.date(1970, 1, 1)
    with open(target/f'{thread[0]}.html', 'w', encoding='utf-8') as f:
        write_prelude(f, thread[4])
        for msg in msgs:
            msg_date = datetime.datetime.fromtimestamp(msg.date/1000).date()
            if msg_date != last_date_written:
                f.write(f'<div class="date">{msg_date}</div>')
                last_date_written = msg_date
            if isinstance(msg, SMS) and msg.body is not None:
                f.write(msg.to_html())
            elif isinstance(msg, MMS):
                f.write(msg.mms_to_html(src, target, cursor))
        write_footer(f)
    return True


def format_group_thread(cursor: sqlite3.Cursor, thread, recips, src: pathlib.Path, target: pathlib.Path) -> bool:
    msgs = load_messages(cursor, thread)
    if not msgs:
        # no results, this thread is empty
        return False
    last_date_written = datetime.date(1970, 1, 1)
    with open(target/f'{thread[0]}.html', 'w', encoding='utf-8') as f:
        write_prelude(f, thread[3])
        for msg in msgs:
            msg_date = datetime.datetime.fromtimestamp(msg.date / 1000).date()
            if msg_date != last_date_written:
                f.write(f'<div class="date">{msg_date.strftime("%Y-%m-%d")}</div>')
                last_date_written = msg_date
            if isinstance(msg, SMS) and msg.body is not None:
                f.write(msg.to_html(recips))
            elif isinstance(msg, MMS):
                f.write(msg.mms_to_html(src, target, cursor, recips))
        write_footer(f)
    return True


def load_messages(cursor, thread):
    sms: list[Message] = [SMS(*m) for m in cursor.execute(
        'select _id, date, NULL, body from sms where thread_id = ? and protocol is NULL union select _id, date, address, body from sms where thread_id = ? and protocol is not null',
        (thread[0], thread[0]))]
    mms: list[Message] = [MMS(*m) for m in cursor.execute(
        'select _id, date, NULL, body from mms where thread_id = ? and m_type = 128 union select _id, date, address, body from mms where thread_id = ? and m_type != 128',
        (thread[0], thread[0]))]
    msgs: list[Message] = sorted(sms + mms, key=lambda x: x.date)
    return msgs


def main(argv):
    src = pathlib.Path(argv[1])
    target = pathlib.Path(argv[2])
    conn = sqlite3.connect(src/'database.sqlite')
    cur = conn.cursor()
    cur.execute('select _id, phone, system_display_name from recipient')
    recipients = {x[0]: (x[2] if x[2] is not None else x[1]) for x in cur.fetchall()}
    cur.execute('select thread._id, thread_recipient_id AS recipient, uuid, phone, system_display_name from thread join recipient r on thread.thread_recipient_id = r._id where group_id is null')
    indiv_threads = cur.fetchall()
    cur.execute('select thread._id, recipient_id, group_id, title from thread join groups g on thread_recipient_id = g.recipient_id')
    group_threads = cur.fetchall()
    prepare_output(target)
    index = open(target/'index.html', 'w')
    for t in indiv_threads:
        print(f"Writing {t[4]}", file=sys.stderr)
        if format_indiv_thread(cur, t, src, target):
            index.write(f'<p><a href="{t[0]}.html">{t[4]}</a></p>')
    for t in group_threads:
        print(f"Writing {t[3]}", file=sys.stderr)
        if format_group_thread(cur, t, recipients, src, target):
            index.write(f'<p><a href="{t[0]}.html">{t[3]}</a></p>')


if __name__ == "__main__":
    sys.exit(main(sys.argv))
