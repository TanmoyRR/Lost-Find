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

        self._mark_read()

    def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            async_to_sync(self.channel_layer.group_discard)(
                self.room_group_name, self.channel_name
            )
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {'type': 'typing_stop', 'user_id': self.user.pk if hasattr(self, 'user') else None}
            )

    def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', 'chat_message')

        if msg_type == 'typing_start':
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {'type': 'typing_start', 'user_id': self.user.pk, 'user_name': self.user.get_full_name() or self.user.username}
            )
            return

        if msg_type == 'typing_stop':
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {'type': 'typing_stop', 'user_id': self.user.pk}
            )
            return

        if msg_type == 'edit_message':
            msg_id = data.get('message_id')
            new_body = data.get('body', '').strip()
            if msg_id and new_body:
                try:
                    msg = Message.objects.get(pk=msg_id, sender=self.user, conversation=self.conversation)
                    msg.edit_message(new_body)
                    async_to_sync(self.channel_layer.group_send)(
                        self.room_group_name,
                        {'type': 'message_edited', 'message_id': msg.pk, 'body': new_body}
                    )
                except Message.DoesNotExist:
                    pass
            return

        if msg_type == 'delete_message':
            msg_id = data.get('message_id')
            if msg_id:
                try:
                    msg = Message.objects.get(pk=msg_id, sender=self.user, conversation=self.conversation)
                    msg.mark_as_deleted()
                    async_to_sync(self.channel_layer.group_send)(
                        self.room_group_name,
                        {'type': 'message_deleted', 'message_id': msg.pk}
                    )
                except Message.DoesNotExist:
                    pass
            return

        body = data.get('body', '').strip()
        if not body or len(body) > 5000:
            return

        msg = Message.objects.create(
            conversation=self.conversation,
            sender=self.user,
            body=body,
        )

        Conversation.objects.filter(pk=self.conversation.pk).update(updated_at=timezone.now())

        other = self.conversation.other_participants(self.user).first()
        if other:
            from django.urls import reverse
            from apps.notifications.models import Notification
            from datetime import timedelta
            recent_notif = Notification.objects.filter(
                user=other, notification_type='message',
                created_at__gte=timezone.now() - timedelta(seconds=5),
            ).exists()
            if not recent_notif:
                Notification.objects.create(
                    user=other,
                    notification_type='message',
                    title=f'New message from {self.user.get_full_name() or self.user.username}',
                    message=body[:200],
                    link=reverse('messaging:detail', args=[self.conversation.pk]),
                )

        timestamp = msg.created_at.strftime('%g:%M %p')

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
        self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'body': event['body'],
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'timestamp': event['timestamp'],
        }))

    def typing_start(self, event):
        if event['user_id'] != self.user.pk:
            self.send(text_data=json.dumps({
                'type': 'typing_start',
                'user_id': event['user_id'],
                'user_name': event['user_name'],
            }))

    def typing_stop(self, event):
        if event['user_id'] != self.user.pk:
            self.send(text_data=json.dumps({
                'type': 'typing_stop',
                'user_id': event['user_id'],
            }))

    def message_edited(self, event):
        self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message_id': event['message_id'],
            'body': event['body'],
        }))

    def message_deleted(self, event):
        self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))

    def _mark_read(self):
        Message.objects.filter(
            conversation=self.conversation,
            is_read=False,
        ).exclude(sender=self.user).update(is_read=True)
