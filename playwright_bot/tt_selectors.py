import re

VIEW_DETAILS = {"role": "button", "name": re.compile(r"view details", re.I)}
REPLY_BTN    = {"role": "button", "name": re.compile(r"(reply|respond)", re.I)}
SEND_BTN     = {"role": "button", "name": re.compile(r"(send|submit)", re.I)}
MESSAGES_TAB = {"role": "link", "name": re.compile(r"^messages$", re.I)}
THREAD_REPLY = re.compile(r"\breply\b", re.I)
SHOW_PHONE = {
    "role": "button",
    "name": re.compile(r"^Click to show phone number$", re.I),
}
MESSAGE_INPUT_PLACEHOLDER = re.compile(
    r"(answer any questions|type your message|message)", re.I
)

LOGIN_LINK = {"role": "link", "name": re.compile(r"(log in|sign in)", re.I)}
LOGIN_BTN  = {"role": "button", "name": re.compile(r"(log in|sign in)", re.I)}
EMAIL_LABEL = re.compile(r"^\s*email\s*(address)?\s*$", re.I)
PASS_LABEL  = re.compile(r"^\s*password\s*$", re.I)

PHONE_REGEX = r"(?:\+?1?[\s-]?)?(?:\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}|\+\d{10,15})"

# Точные селекторы для телефонов на основе реального HTML
PHONE_SHOW_BUTTON = "button:has-text('Click to show phone number')"
PHONE_TEL_LINK = "a[href^='tel:']"
PHONE_DISPLAY_TEXT = "div.IUE7kXgIsvED2G8vml4Wu"

# Дополнительные селекторы для надежности
LEADS_LINK = {"role": "link", "name": re.compile(r"^leads$", re.I)}
PROFILE_LINK = {"role": "link", "name": re.compile(r"^profile$", re.I)}
INBOX_LINK = {"role": "link", "name": re.compile(r"^inbox$", re.I)}

# Альтернативные селекторы для кнопок
VIEW_DETAILS_ALT = re.compile(r"(view\s+details|see\s+details)", re.I)
REPLY_ALT = re.compile(r"(reply|respond|answer)", re.I)
SEND_ALT = re.compile(r"(send|submit|post)", re.I)