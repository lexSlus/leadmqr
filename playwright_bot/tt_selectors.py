import re

VIEW_DETAILS = {"role": "button", "name": re.compile(r"view details", re.I)}
REPLY_BTN    = {"role": "button", "name": re.compile(r"(reply|respond)", re.I)}
SEND_BTN     = {"role": "button", "name": re.compile(r"(send|submit)", re.I)}
MESSAGES_TAB = {"role": "link", "name": re.compile(r"^messages$", re.I)}
THREAD_REPLY = re.compile(r"\breply\b", re.I)
SHOW_PHONE = {
    "role": "button",
    "name": re.compile(r"(click to show phone number|show phone number)", re.I),
}
MESSAGE_INPUT_PLACEHOLDER = re.compile(
    r"(answer any questions|type your message|message)", re.I
)

LOGIN_LINK = {"role": "link", "name": re.compile(r"(log in|sign in)", re.I)}
LOGIN_BTN  = {"role": "button", "name": re.compile(r"(log in|sign in)", re.I)}
EMAIL_LABEL = re.compile(r"^\s*email\s+address\s*$", re.I)
PASS_LABEL  = re.compile(r"^\s*password\s*$", re.I)

PHONE_REGEX = r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4})"