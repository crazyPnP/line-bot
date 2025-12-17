from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient,
    ReplyMessageRequest, TextMessage
)
from config import LINE_CHANNEL_ACCESS_TOKEN
from services.proposal_service import ProposalService
from services.booking_service import BookingService

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
proposal_service = ProposalService()
booking_service = BookingService()


def handle_event(event):
    if not isinstance(event, MessageEvent):
        return
    if not isinstance(event.message, TextMessageContent):
        return

    text = event.message.text.strip()
    line_user_id = event.source.user_id

    reply = "指令未支援"

    if text == "提案":
        reply = proposal_service.start_create_proposal(line_user_id)

    elif text.startswith("接受"):
        # 例：接受 3
        idx = int(text.split()[1])
        reply = proposal_service.accept_by_index(line_user_id, idx)

    elif text.startswith("取消"):
        idx = int(text.split()[1])
        reply = booking_service.cancel_by_index(line_user_id, idx)

    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)
        api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply)]
            )
        )
