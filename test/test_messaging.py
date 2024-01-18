import unittest
from unittest.mock import patch, MagicMock

from orjson import orjson

import testing_data
from phanos.messaging import BlockingPublisher


class TestMessaging(unittest.TestCase):
    def setUp(self):
        self.publisher = BlockingPublisher()

    def tearDown(self):
        self.publisher = None

    def test_is_connected(self):
        self.assertFalse(self.publisher.is_connected())
        self.publisher.connection = MagicMock()
        self.assertTrue(self.publisher.is_connected())

    def test_is_bound(self):
        self.assertFalse(self.publisher._is_bound())
        self.publisher.channel = MagicMock()
        self.assertTrue(self.publisher._is_bound())

    def test_bool(self):
        self.assertFalse(self.publisher)
        self.publisher.connection = MagicMock()
        self.publisher.channel = MagicMock()
        self.assertTrue(self.publisher)

    def test_close(self):
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        self.publisher.connection = mock_connection
        self.publisher.channel = mock_channel
        self.publisher.close()
        mock_channel.close.assert_called_once()
        mock_connection.close.assert_called_once()
        self.publisher.connection = None
        self.publisher.channel = None

    @patch("pika.BlockingConnection", autospec=True)
    def test_connect(self, mock_connection: MagicMock):
        self.publisher.connect()
        mock_connection.assert_called_once()

    @patch("test.test_messaging.BlockingPublisher.close")
    @patch("test.test_messaging.BlockingPublisher.connect")
    def test_reconnect(self, mock_connect: MagicMock, mock_close: MagicMock):
        publisher = BlockingPublisher()
        publisher.reconnect()
        mock_close.assert_called_once()
        mock_connect.assert_called_once()

        mock_connect.side_effect = ConnectionError()
        with self.assertRaises(ConnectionError):
            publisher.reconnect()

        publisher.reconnect(True)

    @patch("test.test_messaging.BlockingPublisher.close")
    @patch("test.test_messaging.BlockingPublisher.connect")
    def test_check_or_rebound(self, mock_connect: MagicMock, mock_close: MagicMock):
        publisher = BlockingPublisher()
        publisher.check_or_rebound()
        mock_close.assert_called_once()
        mock_connect.assert_called_once()

        mock_connect.reset_mock()
        publisher.connection = MagicMock()
        publisher.channel = MagicMock()
        publisher.check_or_rebound()
        mock_connect.assert_not_called()

    @patch("test.test_messaging.BlockingPublisher.close")
    @patch("test.test_messaging.BlockingPublisher.connect")
    @patch("test.test_messaging.BlockingPublisher.reconnect")
    def test_publish(self, mock_reconnect: MagicMock, mock_connect: MagicMock, mock_close: MagicMock):
        _ = mock_connect
        _ = mock_close
        mock_channel = MagicMock()
        publisher = BlockingPublisher()
        publisher.channel = mock_channel
        self.assertTrue(publisher.publish(testing_data.test_handler_in))
        mock_channel.basic_publish.assert_called_once_with(
            exchange=publisher.exchange_name,
            body=orjson.dumps(testing_data.test_handler_in),
            routing_key=testing_data.test_handler_in["job"],
        )
        mock_channel.reset_mock()
        mock_channel.basic_publish.side_effect = ConnectionError()
        publisher.connection_parameters.retry_delay = 0
        publisher.retry = 2
        self.assertFalse(publisher.publish(testing_data.test_handler_in))
        self.assertEqual(mock_channel.basic_publish.call_count, 2 + 1)
        self.assertEqual(mock_reconnect.call_count, 2 + 1)
