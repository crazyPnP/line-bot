from linebot.v3.messaging import MessagingApi, ApiClient, Configuration, PushMessageRequest, TextMessage

class LinePushService:
    def __init__(self, configuration: Configuration):
        self.api = MessagingApi(ApiClient(configuration))

    def push_text(self, to_line_user_id: str, text: str):
        self.api.push_message(
            PushMessageRequest(
                to=to_line_user_id,
                messages=[TextMessage(text=text)]
            )
        )
