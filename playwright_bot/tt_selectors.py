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
# Альтернативный селектор для кнопки показа телефона
SHOW_PHONE_BUTTON = "button:has-text('Click to show phone number')"
# Селектор для кнопки по классу (из HTML)
SHOW_PHONE_BUTTON_CLASS = "button._3HFh8Wm0kL8FRvqW7u0LOA"
# Селектор для уже показанного телефона
PHONE_LINK = "a[href^='tel:']"
# Селектор для скрытого телефона (с классом dn)
HIDDEN_PHONE_LINK = "div.dn a[href^='tel:']"
MESSAGE_INPUT_PLACEHOLDER = re.compile(
    r"(answer any questions|type your message|message)", re.I
)

LOGIN_LINK = {"role": "link", "name": re.compile(r"(log in|sign in)", re.I)}
LOGIN_BTN  = {"role": "button", "name": re.compile(r"(log in|sign in)", re.I)}
EMAIL_LABEL = re.compile(r"^\s*email\s+address\s*$", re.I)
PASS_LABEL  = re.compile(r"^\s*password\s*$", re.I)

# Альтернативные селекторы для полей ввода
EMAIL_INPUT = {"placeholder": "Email"}
PASS_INPUT = {"placeholder": "Password"}
LOGIN_SUBMIT = {"role": "button", "name": "Log in"}

PHONE_REGEX = r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4})"