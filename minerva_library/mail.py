import smtplib
import json
import datetime
import random

# import ipdb : not used anymore
import sys
import socket
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

sys.dont_write_bytecode = True
import os


def send(
    subject,
    body,
    level="normal",
    attachments=[],
    logger=None,
    directory="directory.txt",
):
    # 	return
    host = socket.gethostname()
    if host == "Main":
        credential_directory = "/home/minerva/minerva-control/credentials/"
    elif host == "HIRO":
        credential_directory = "/home/legokid/pyminerva/credentials/"
    else:
        credential_directory = "C:/minerva-control/credentials/"
    # read in the contacts directory (proprietary)
    with open(credential_directory + directory) as dirfile:
        directory = json.load(dirfile)

    # filter recipients according to alert level, preferences
    hournow = datetime.datetime.utcnow().hour
    recipients = []
    for contact in directory:
        if level in contact["levels"]:
            if (
                hournow <= contact["forbiddenwindow"][0]
                or hournow >= contact["forbiddenwindow"][1]
            ):
                if random.random() < contact["probability"]:
                    recipients.append(contact["email"])

    if len(recipients) == 0:
        return

    # login credentials (proprietary)
    f = open(credential_directory + "emaillogin.txt")
    username = f.readline()
    password = f.readline()
    f.close()

    # Prep email
    msg = MIMEMultipart()
    # 	msg = MIMEText(body)
    msg["From"] = username.strip()
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body))

    # doesn't work for pdf attachments (only tested for pngs)
    for attachment in attachments:
        if os.path.exists(attachment):
            fp = open(attachment, "rb")
            img = MIMEImage(fp.read(), name=os.path.basename(attachment))
            fp.close()
            msg.attach(img)

    # send email
    server = smtplib.SMTP("smtp.gmail.com")
    server.starttls()
    server.login(username, password)
    try:
        server.sendmail(username, recipients, msg.as_string())
    except:
        if logger != None:
            logger.exception("****SENDMAIL FAILED****")
        else:
            print("****SENDMAIL FAILED****")
    server.quit()


if __name__ == "__main__":
    send("test subject", "body of email")
