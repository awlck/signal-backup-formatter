# signal-backup-formatter

After decrypting and extracting an Android Signal backup, you can use this tool to render the chats inside in HTML form.
To run this, you only need Python 3.

## How to use
1. Decrypt and extract the backup using [bepaald/signalbackup-tools](https://github.com/bepaald/signalbackup-tools). E.g.:
  ```
  ./signalbackup-tools signal-2021-10-20-10-33-59.backup <30-digit pin> --output raw/
  ```
2. Run this tool, giving the folder into which you just extracted your backup, as well as where you would like the generated
  HTML files to be placed:
  ```
  python3 signal_formatter.py ./raw ./html
  ```
3. Open `index.html` from the output folder in your browser and select a thread to read.
