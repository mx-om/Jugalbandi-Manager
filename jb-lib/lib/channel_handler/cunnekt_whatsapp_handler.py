import base64
import logging
import json
from typing import Any, Dict, Generator
import requests

from sqlalchemy import select

from ..db_session_handler import DBSessionHandler
from .channel_handler import ChannelData, User
from .rest_channel_handler import RestChannelHandler
from .language import LanguageMapping, LanguageCodes
from ..data_models import (
    MessageType,
    Message,
    TextMessage,
    AudioMessage,
    InteractiveMessage,
    Option,
    FormMessage,
    ImageMessage,
    DocumentMessage,
    InteractiveReplyMessage,
    RestBotInput,
    ListMessage,
    ButtonMessage,
    DialogMessage,
    DialogOption,
    FormReplyMessage,
)
from ..models import JBChannel, JBUser, JBForm
from ..encryption_handler import EncryptionHandler

logger = logging.getLogger(__name__)


class CunnektWhatsappHandler(RestChannelHandler):

    @classmethod
    def is_valid_data(cls, data: Dict) -> bool:
        # return "object" in data and data["object"] == "whatsapp_business_account"
        return "object"

    @classmethod
    def process_message(cls, data: Dict) -> Generator[ChannelData, None, None]:
        # if cls.is_valid_data(data):
        #     for entry in data["entry"]:
        #         for change in entry["changes"]:
        #             if "value" in change:
        #                 if "messages" in change["value"]:
        #                     for message in change["value"]["messages"]:
        #                         message.pop("id", None)
        #                         message.pop("context", None)
        #                         user_identifier = message.pop("from")
        #                         yield ChannelData(
        #                             user=User(
        #                                 user_identifier=user_identifier,
        #                                 user_name="Dummy",
        #                                 user_phone=user_identifier,
        #                             ),
        #                             message_data=message,
        #                         )
        
        # for entry in data["entry"]:
            # for change in entry["changes"]:
            #     if "value" in change:
            #         if "messages" in change["value"]:
        logger.error(f"Data in Process msg {data}")
        if data["messaging_product"] == "whatsapp" and "messages" in data:

            for message in data["messages"]:
                message.pop("id", None)
                message.pop("context", None)
                user_identifier = message.pop("from")
                yield ChannelData(
                    user=User(
                        user_identifier=user_identifier,
                        user_name="Dummy",
                        user_phone=user_identifier,
                    ),
                    message_data=message,
                )

    @classmethod
    def get_channel_name(cls) -> str:
        return "cunnekt_whatsapp"

    @classmethod
    def get_message_type(cls, bot_input: RestBotInput) -> MessageType:
        data = bot_input.data
        message_type = data["type"]
        message_data = data[message_type]
        if message_type == "text":
            return MessageType.TEXT
        elif message_type == "audio":
            return MessageType.AUDIO
        elif message_type == "interactive":
            interactive_type = message_data["type"]
            if interactive_type == "button_reply":
                return MessageType.INTERACTIVE_REPLY
            elif interactive_type == "list_reply":
                interactive_message_data = message_data[interactive_type]
                if interactive_message_data["id"].startswith("lang_"):
                    return MessageType.DIALOG
                return MessageType.INTERACTIVE_REPLY
            elif interactive_type == "nfm_reply":
                return MessageType.FORM_REPLY
        return NotImplemented

    @classmethod
    def to_text_message(cls, bot_input: RestBotInput) -> TextMessage:
        data = bot_input.data
        message_type = data["type"]
        message_data = data[message_type]
        text = message_data["body"]
        return TextMessage(body=text)

    @classmethod
    def get_audio(cls, channel: JBChannel, bot_input: RestBotInput) -> bytes:
        data = bot_input.data
        message_type = data["type"]
        message_data = data[message_type]
        audio_id = message_data["id"]
        audio_content = cls.wa_download_audio(channel=channel, file_id=audio_id)
        return audio_content

    @classmethod
    def to_interactive_reply_message(
        cls, bot_input: RestBotInput
    ) -> InteractiveReplyMessage:
        data = bot_input.data
        message_type = data["type"]
        message_data = data[message_type]
        interactive_type = message_data["type"]
        interactive_message_data = message_data[interactive_type]
        options = [
            Option(
                option_id=interactive_message_data["id"],
                option_text=interactive_message_data["title"],
            )
        ]
        return InteractiveReplyMessage(options=options)

    @classmethod
    def to_dialog_message(cls, bot_input: RestBotInput) -> DialogMessage:
        data = bot_input.data
        message_type = data["type"]
        message_data = data[message_type]
        interactive_type = message_data["type"]
        interactive_message_data = message_data[interactive_type]
        selected_language = interactive_message_data["id"]
        selected_language = selected_language.replace("lang_", "").upper()
        return DialogMessage(
            dialog_id=DialogOption.LANGUAGE_SELECTED,
            dialog_input=LanguageCodes[selected_language].value.lower(),
        )

    @classmethod
    def to_form_reply_message(cls, bot_input: RestBotInput) -> FormReplyMessage:
        data = bot_input.data
        message_type = data["type"]
        message_data = data[message_type]
        interactive_type = message_data["type"]
        interactive_message_data = message_data[interactive_type]
        return FormReplyMessage(form_data=interactive_message_data["response_json"])

    @classmethod
    def parse_bot_output(
        cls, message: Message, user: JBUser, channel: JBChannel
    ) -> Dict:
        message_type = message.message_type
        if message_type == MessageType.TEXT:
            data = cls.parse_text_message(
                channel=channel, user=user, message=message.text
            )
        elif message_type == MessageType.AUDIO:
            data = cls.parse_audio_message(
                channel=channel, user=user, message=message.audio
            )
        elif message_type == MessageType.BUTTON:
            data = cls.parse_button_message(
                channel=channel,
                user=user,
                message=message.button,
            )
        elif message_type == MessageType.OPTION_LIST:
            data = cls.parse_list_message(
                channel=channel, user=user, message=message.option_list
            )
        elif message_type == MessageType.IMAGE:
            data = cls.parse_image_message(
                channel=channel,
                user=user,
                message=message.image,
            )
        elif message_type == MessageType.DOCUMENT:
            data = cls.parse_document_message(
                channel=channel,
                user=user,
                message=message.document,
            )
        elif message_type == MessageType.FORM:
            data = cls.parse_form_message(
                channel=channel,
                user=user,
                message=message.form,
            )
        elif message_type == MessageType.DIALOG:
            data = cls.parse_dialog_message(
                channel=channel,
                user=user,
                message=message.dialog,
            )
        else:
            return NotImplemented
        return data

    @classmethod
    def parse_text_message(
        cls, channel: JBChannel, user: JBUser, message: TextMessage
    ) -> Dict[str, Any]:
        # data = {
        #     "messaging_product": "whatsapp",
        #     "preview_url": False,
        #     "recipient_type": "individual",
        #     "to": str(user.identifier),
        #     "type": "text",
        #     "text": {"body": str(message.body)},
        # }

        data = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "mobile": str(user.identifier),
            "type": "text",
            "text": str(message.body),
        }

        return data

    @classmethod
    def parse_audio_message(
        cls, channel: JBChannel, user: JBUser, message: AudioMessage
    ) -> Dict[str, Any]:
        # data = {
        #     "messaging_product": "whatsapp",
        #     "preview_url": False,
        #     "recipient_type": "individual",
        #     "to": str(user.identifier),
        #     "type": "audio",
        #     "audio": {"link": message.media_url},
        # }

        data = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "mobile": str(user.identifier),
            "type": "audio",
            "audio": message.media_url,
            "caption": "audio"
        }

        return data

    @classmethod
    def parse_list_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: ListMessage,
    ) -> Dict[str, Any]:
        # list_message_data = {
        #     "messaging_product": "whatsapp",
        #     "preview_url": False,
        #     "recipient_type": "individual",
        #     "to": str(user.identifier),
        #     "type": "interactive",
        #     "interactive": {
        #         "type": "list",
        #         "header": {
        #             "type": "text",
        #             "text": message.header[:59] if message.header else "",
        #         },
        #         "body": {"text": message.body},
        #         "footer": {"text": message.footer},
        #         "action": {
        #             "button": message.button_text,
        #             "sections": [
        #                 {
        #                     "title": message.list_title,
        #                     "rows": [
        #                         {
        #                             "id": option.option_id,
        #                             "title": option.option_text[:20],
        #                         }
        #                         for option in message.options
        #                     ],
        #                 }
        #             ],
        #         },
        #     },
        # }


        list_message_data = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "mobile": str(user.identifier),
            "type": "list",
            "header": {
                    "type": "text",
                    "text": message.header[:59] if message.header else "",
                },

            "footer": {"text": message.footer},
            "list_title": message.list_title,
            "list": [
                {
                    "id": option.option_id,
                    "title": option.option_text[:20],
                }
                for option in message.options
            ],

             "body": message.body,

            
         
        }

        return list_message_data

    @classmethod
    def parse_button_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: ButtonMessage,
    ) -> Dict[str, Any]:
        # button_message_data = {
        #     "messaging_product": "whatsapp",
        #     "preview_url": False,
        #     "recipient_type": "individual",
        #     "to": str(user.identifier),
        #     "type": "interactive",
        #     "interactive": {
        #         "type": "button",
        #         "header": {
        #             "type": "text",
        #             "text": message.header[:59] if message.header else "",
        #         },
        #         "body": {"text": message.body},
        #         "footer": {"text": message.footer},
        #         "action": {
        #             "buttons": [
        #                 {
        #                     "type": "reply",
        #                     "reply": {"id": x.option_id, "title": x.option_text[:20]},
        #                 }
        #                 for x in message.options
        #             ],
        #         },
        #     },
        # }

        button_message_data = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "mobile": str(user.identifier),
            "type": "button",
            "header": {
                "type": "text",
                "text": message.header[:59] if message.header else "",
            },
            "body": message.body,
            "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": x.option_id, "title": x.option_text[:20]},
                        }
                        for x in message.options
                    ],

        }

        return button_message_data

    @classmethod
    def parse_interactive_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: InteractiveMessage,
    ) -> Dict[str, Any]:
        if isinstance(message, ListMessage):
            data = cls.parse_list_message(channel, user, message)
        elif isinstance(message, ButtonMessage):
            data = cls.parse_button_message(channel, user, message)
        else:
            return NotImplemented
        return data

    @classmethod
    def parse_image_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: ImageMessage,
    ) -> Dict[str, Any]:
        # data = {
        #     "messaging_product": "whatsapp",
        #     "preview_url": False,
        #     "recipient_type": "individual",
        #     "to": str(user.identifier),
        #     "type": "image",
        #     "image": {"link": message.url, "caption": message.caption},
        # }

        data = {
                "messaging_product": "whatsapp",
                "preview_url": False,
                "recipient_type": "individual",
                "mobile": str(user.identifier),
                "type": "image",
                "image": message.url,
                "caption": message.caption
        }
        
        return data

    @classmethod
    def parse_document_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: DocumentMessage,
    ) -> Dict[str, Any]:
        # data = {
        #     "messaging_product": "whatsapp",
        #     "preview_url": False,
        #     "recipient_type": "individual",
        #     "to": str(user.identifier),
        #     "type": "document",
        #     "document": {
        #         "link": message.url,
        #         "filename": message.name,
        #         "caption": message.caption,
        #     },
        # }

        data = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "mobile": str(user.identifier),
            "type": "document",

            "document": message.url,
            "caption": message.caption,
        }

        return data

    @classmethod
    def get_form_parameters(cls, form_id: str):
        # Create a query to insert a new row into JBPluginMapping
        with DBSessionHandler.get_sync_session() as session:
            with session.begin():
                result = session.execute(select(JBForm).where(JBForm.id == form_id))
                s = result.scalars().first()
                return s

    @classmethod
    def parse_form_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: FormMessage,
    ) -> Dict[str, Any]:
        form_id = message.form_id

        form_parameters = cls.get_form_parameters(form_id)
        data = {
            "messaging_product": "whatsapp",
            "preview_url": False,
            "recipient_type": "individual",
            "to": str(user.identifier),
            "type": "interactive",
            "interactive": {
                "type": "flow",
                "body": {"text": message.body},
                "footer": {"text": message.footer},
                "action": {
                    "name": "flow",
                    "parameters": form_parameters,
                },
            },
        }
        return data

    @classmethod
    def parse_dialog_message(
        cls,
        channel: JBChannel,
        user: JBUser,
        message: DialogMessage,
    ) -> Dict[str, Any]:
        if message.dialog_id == DialogOption.LANGUAGE_CHANGE:
            languages = [
                Option(
                    option_id=f"lang_{language.lower()}",
                    option_text=representation.value,
                )
                for language, representation in LanguageMapping.__members__.items()
            ]
            language_message = ListMessage(
                header="Language",
                body="Please select your preferred language",
                footer="भाषा चुनें",
                options=languages[:10],
                button_text="चुनें / Select",
                list_title="भाषाएँ / Languages",
            )
            return cls.parse_list_message(channel, user, language_message)
        return NotImplemented

    @classmethod
    def generate_header(cls, channel: JBChannel):
        encryption_key: str = str(channel.key)
        decrypted_key = EncryptionHandler.decrypt_text(encryption_key)
        # headers = {
        #     "Content-type": "application/json",
        #     "wanumber": channel.app_id,
        #     "apikey": decrypted_key,
        # }

        headers = {
            "Content-type": "application/json",
            "API-KEY": decrypted_key,
        }
        return headers

    @classmethod
    def send_message(cls, channel: JBChannel, user: JBUser, message: Message):
        # url = f"{channel.url}/v1/messages"
        url = f"{channel.url}/sendreplymessage"
        headers = cls.generate_header(channel=channel)
        data = cls.parse_bot_output(message=message, channel=channel, user=user)
        logger.error(f"Data in send messgae {data}")
        logger.error(f"Header in send messgae {headers}")
        logger.error(f"API URL in send messgae {url}")
        r = requests.post(url, data=json.dumps(data), headers=headers)
        json_output = r.json()
        logger.error("get msg response: %s", json_output)

        if json_output and "messages" in json_output and json_output["messages"]:
            return json_output["messages"][0]["id"]
        else:
            logger.error(f"Error sending message: {json_output}")
        return None

    @classmethod
    def wa_download_audio(cls, channel: JBChannel, file_id: str):
        url = f"{channel.url}/v1/downloadmedia/{file_id}"
        headers = cls.generate_header(channel=channel)
        r = requests.get(url, headers=headers)
        file_content = base64.b64encode(r.content)
        return file_content
