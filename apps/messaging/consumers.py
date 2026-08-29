import json
import logging

from channels.generic.websocket import WebsocketConsumer
from channels.exceptions import StopConsumer
from asgiref.sync import async_to_sync
from django.utils import timezone

from .models import Conversation, Message
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


class ChatConsumer(WebsocketConsumer):
    """
    WebSocket consumer for real-time chat within a conversation.
    """

    def connect(self):
        self.user = self.scope.get('user')
        if not self.user or self.user.is_anonymous:
            self.close()
            return

        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'

        try:
            self.conversation = Conversation.objects.get(pk=self.conversation_id)
        except Conversation.DoesNotExist:
            self.close()
            return

        if not self.conversation.participants.filter(pk=self.user.pk).exists():
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name, self.channel_name
        )
        self.accept()

        # Mark incoming messages as read
        self._mark_read()

    def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name, self.channel_name
            )

    def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        body = data.get('body', '').strip()
        if not body:
            return

        msg = Message.objects.create(
            conversation=self.conversation,
            sender=self.user,
            body=body,
        )

        # Update conversation timestamp
        self.conversation.save()

        # Notify the other participant
        other = self.conversation.other_participants(self.user).first()
        if other:
            Notification.objects.create(
                user=other,
                notification_type='message',
                title=f'New message from {self.user.get_full_name() or self.user.username}',
                message=body[:200],
                link=f'/messages/{self.conversation.pk}/',
            )

        timestamp = msg.created_at.strftime('%g:%M %p')

        # Broadcast to the group (both participants)
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message_id': msg.pk,
                'body': body,
                'sender_id': self.user.pk,
                'sender_name': self.user.get_full_name() or self.user.username,
                'timestamp': timestamp,
            }
        )

    def chat_message(self, event):
        """Send message to WebSocket."""
        self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'body': event['body'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'timestamp': event['timestamp'],
        }))

    def _mark_read(self):
        """Mark unread messages from the other user as read."""
        Message.objects.filter(
            conversation=self.conversation,
            is_read=False,
        ).exclude(sender=self.user).update(is_read=True)
